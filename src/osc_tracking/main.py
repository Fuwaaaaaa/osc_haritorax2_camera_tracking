"""Entry point for the OSC Tracking system."""

import argparse
import logging
import signal
import sys
import time

from .camera_tracker import CameraConfig, CameraTracker
from .config import TrackingConfig
from .fusion_engine import FusionEngine
from .gesture_detector import GestureDetector
from .motion_smoothing import get_preset
from .notifications import NotificationManager
from .osc_receiver import OSCReceiver
from .osc_remapper import OSCRemapper
from .osc_sender import OSCSender
from .preflight import PreflightIssue, run_preflight_checks
from .profiler import PerformanceProfiler
from .quality_meter import QualityLevel, QualityMeter
from .state_machine import TrackingMode
from .web_dashboard import WebDashboard

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


class SubsystemManager:
    """Manages optional subsystem lifecycle (start/stop)."""

    def __init__(self):
        self._subsystems: list[tuple[str, object]] = []

    def add(self, name: str, subsystem: object) -> None:
        self._subsystems.append((name, subsystem))

    def get(self, name: str) -> object | None:
        for n, s in self._subsystems:
            if n == name:
                return s
        return None

    def start_all(self) -> None:
        for name, sub in self._subsystems:
            if hasattr(sub, "start"):
                sub.start()
            elif hasattr(sub, "connect"):
                sub.connect()

    def stop_all(self) -> None:
        for name, sub in reversed(self._subsystems):
            try:
                if hasattr(sub, "stop"):
                    sub.stop()
                elif hasattr(sub, "close"):
                    sub.close()
            except Exception as e:
                logger.warning("Error stopping %s: %s", name, e)

# ANSI colors for mode display
MODE_COLORS = {
    TrackingMode.VISIBLE: "\033[92m",           # green
    TrackingMode.PARTIAL_OCCLUSION: "\033[93m",  # yellow
    TrackingMode.FULL_OCCLUSION: "\033[91m",     # red
    TrackingMode.IMU_DISCONNECTED: "\033[91m",   # red
    TrackingMode.SINGLE_CAM_DEGRADED: "\033[93m", # yellow
    TrackingMode.FUTON_MODE: "\033[96m",          # cyan
}
RESET = "\033[0m"


def _mode_to_quality_level(mode: TrackingMode) -> QualityLevel:
    if mode == TrackingMode.VISIBLE:
        return QualityLevel.GOOD
    if mode in (TrackingMode.PARTIAL_OCCLUSION, TrackingMode.SINGLE_CAM_DEGRADED):
        return QualityLevel.WARNING
    if mode in (TrackingMode.FULL_OCCLUSION, TrackingMode.IMU_DISCONNECTED):
        return QualityLevel.ERROR
    return QualityLevel.OFFLINE


def _snapshot_to_joint_dict(snapshot) -> dict:
    """Convert a SkeletonSnapshot into the legacy tuple dict expected by
    existing subsystem interfaces (recorder, vmc_sender, bvh, viewer).

    Shape: ``{joint_name: (position_ndarray, rotation, confidence)}``.
    """
    return {
        bone.name: (js.position.to_array(), js.rotation, float(js.confidence))
        for bone, js in snapshot.joints.items()
    }


def _joint_positions(snap) -> dict:
    return {bone.name: js.position.to_array() for bone, js in snap.joints.items()}


def _avg_confidence(snap) -> float:
    confs = [float(js.confidence) for js in snap.joints.values()]
    return sum(confs) / len(confs) if confs else 0.0


def _joint_confidence_dict(snap) -> dict:
    return {bone.name: {"conf": float(js.confidence)} for bone, js in snap.joints.items()}


def _pos_rot_dict(snap) -> dict:
    return {bone.name: (js.position.to_array(), js.rotation) for bone, js in snap.joints.items()}


# Per-subsystem FrameProcessed handlers. Each one takes the concrete
# subsystem and the event, so ``functools.partial(handler, subsystem)``
# produces a one-argument callable the EventBus can dispatch. Keeping
# them module-level (rather than inside a closure) lets a new subsystem
# be added by defining one more handler and one more bus.subscribe call
# in _wire_event_subscribers — the main loop itself stays untouched.

def _handle_frame_gesture(gesture, event) -> None:
    positions = _joint_positions(event.snapshot)
    if not positions:
        return
    detected = gesture.update(positions)
    if detected:
        logger.info("Gesture detected: %s", detected)


def _handle_frame_tray(tray, event) -> None:
    snap = event.snapshot
    tray.update(_mode_to_quality_level(snap.mode), snap.mode.name, event.fps)


def _handle_frame_dashboard(dashboard, event) -> None:
    snap = event.snapshot
    dashboard.update(
        snap.mode.name, event.fps, _avg_confidence(snap), _joint_confidence_dict(snap)
    )


def _handle_frame_recorder(recorder, event) -> None:
    snap = event.snapshot
    if not snap.joints:
        return
    recorder.record_frame(_snapshot_to_joint_dict(snap), snap.mode.name)


def _handle_frame_vmc(vmc_sender, event) -> None:
    snap = event.snapshot
    if not snap.joints:
        return
    vmc_sender.send_frame(_pos_rot_dict(snap))


def _handle_frame_bvh(bvh, event) -> None:
    snap = event.snapshot
    if not snap.joints:
        return
    bvh.add_frame(_pos_rot_dict(snap))


def _handle_frame_viewer(viewer, event) -> None:
    positions = _joint_positions(event.snapshot)
    if not positions:
        return
    viewer.update(positions)


def _handle_frame_discord(discord, event) -> None:
    discord.update(event.snapshot.mode.name, event.fps)


def _handle_frame_api(api, event) -> None:
    snap = event.snapshot
    api.update(snap.mode.name, event.fps, _joint_confidence_dict(snap))


def _handle_frame_obs(obs_overlay, event) -> None:
    snap = event.snapshot
    obs_overlay.update(snap.mode.name, event.fps, _avg_confidence(snap))


def _wire_event_subscribers(
    bus,
    *,
    tray=None,
    dashboard=None,
    recorder=None,
    vmc_sender=None,
    bvh=None,
    viewer=None,
    discord=None,
    api=None,
    obs_overlay=None,
    gesture=None,
    notifier=None,
) -> None:
    """Subscribe each enabled subsystem to the events it cares about.

    Each subsystem that is present gets its own FrameProcessed
    subscriber via ``functools.partial`` against a module-level
    handler. Adding a new output is one more handler plus one more
    ``bus.subscribe`` call — no surgery on a shared on_frame closure.
    """
    from functools import partial

    from .domain.events import (
        FrameProcessed,
        IMUDisconnected,
        IMUReconnected,
        TrackingModeChanged,
    )

    subsystem_bindings = (
        (gesture, _handle_frame_gesture),
        (tray, _handle_frame_tray),
        (dashboard, _handle_frame_dashboard),
        (recorder, _handle_frame_recorder),
        (vmc_sender, _handle_frame_vmc),
        (bvh, _handle_frame_bvh),
        (viewer, _handle_frame_viewer),
        (discord, _handle_frame_discord),
        (api, _handle_frame_api),
        (obs_overlay, _handle_frame_obs),
    )
    for subsystem, handler in subsystem_bindings:
        if subsystem is not None:
            bus.subscribe(FrameProcessed, partial(handler, subsystem))

    if notifier is not None:
        def on_mode_changed(event: TrackingModeChanged) -> None:
            if event.current == TrackingMode.FULL_OCCLUSION:
                notifier.notify_camera_lost(0)
            elif (
                event.current == TrackingMode.VISIBLE
                and event.previous == TrackingMode.FULL_OCCLUSION
            ):
                notifier.notify_camera_recovered(0)

        def on_imu_disconnected(_event: IMUDisconnected) -> None:
            notifier.notify_disconnect()

        def on_imu_reconnected(_event: IMUReconnected) -> None:
            notifier.notify_reconnect()

        bus.subscribe(TrackingModeChanged, on_mode_changed)
        bus.subscribe(IMUDisconnected, on_imu_disconnected)
        bus.subscribe(IMUReconnected, on_imu_reconnected)


def _build_receiver(cfg: TrackingConfig):
    """Select and instantiate the IMU receiver based on config.

    Returns an object conforming to the ``IMUReceiver`` protocol.
    """
    if cfg.receiver_type == "ble":
        if not cfg.ble_local_name_to_bone:
            logger.warning(
                "receiver_type='ble' but ble_local_name_to_bone is empty; no peripherals will be mapped. "
                "Run `python -m osc_tracking.tools.ble_scan` to discover devices, then populate config."
            )
        try:
            from .ble_receiver import BLEReceiver
        except ImportError as exc:
            logger.error(
                "Cannot import BLEReceiver (bleak missing?): %s. Falling back to OSC.", exc
            )
            return OSCReceiver(host=cfg.osc_receive_host, port=cfg.osc_receive_port)
        return BLEReceiver(
            local_name_to_bone=cfg.ble_local_name_to_bone,
            name_prefix=cfg.ble_device_name_prefix,
            scan_timeout_sec=cfg.ble_scan_timeout_sec,
        )
    if cfg.receiver_type == "serial":
        if not cfg.serial_port:
            logger.error(
                "receiver_type='serial' but serial_port is empty; falling back to OSC. "
                "Set serial_port in config (e.g. 'COM3') or pass --port."
            )
            return OSCReceiver(host=cfg.osc_receive_host, port=cfg.osc_receive_port)
        if not cfg.serial_tracker_id_to_bone:
            logger.warning(
                "receiver_type='serial' but serial_tracker_id_to_bone is empty; no trackers will be mapped."
            )
        try:
            from .serial_receiver import SerialReceiver
        except ImportError as exc:
            logger.error(
                "Cannot import SerialReceiver (pyserial missing?): %s. Falling back to OSC.", exc
            )
            return OSCReceiver(host=cfg.osc_receive_host, port=cfg.osc_receive_port)
        return SerialReceiver(
            port=cfg.serial_port,
            baudrate=cfg.serial_baudrate,
            tracker_id_to_bone=cfg.serial_tracker_id_to_bone,
        )
    if cfg.receiver_type != "osc":
        logger.warning(
            "Unknown receiver_type=%r; falling back to OSC. Valid values: 'osc', 'ble', 'serial'.",
            cfg.receiver_type,
        )
    # default: OSC via SlimeVR Server
    return OSCReceiver(host=cfg.osc_receive_host, port=cfg.osc_receive_port)


def main() -> None:
    parser = argparse.ArgumentParser(description="OSC Tracking - IMU Tracker + Dual WebCam Sensor Fusion")
    parser.add_argument("--config", type=str, help="Path to config JSON file")
    parser.add_argument("--cam1", type=int, help="Camera 1 index")
    parser.add_argument("--cam2", type=int, help="Camera 2 index")
    parser.add_argument(
        "--cams",
        type=str,
        help="Comma-separated camera indices, e.g. '0,1' (stereo) or '0' (mono). "
             "Overrides --cam1/--cam2 when set.",
    )
    parser.add_argument(
        "--receiver",
        choices=["osc", "ble", "serial"],
        help="IMU receiver: 'osc' (SlimeVR Server, default), 'ble' (direct HaritoraX2, experimental), "
             "or 'serial' (GX6/GX2 dongle or SPP COM port, experimental)",
    )
    parser.add_argument("--osc-port", type=int, help="OSC receive port")
    parser.add_argument(
        "--ble-device",
        type=str,
        help="BLE advertising name prefix (default from config, e.g. 'HaritoraX2-')",
    )
    parser.add_argument(
        "--port",
        type=str,
        help="Serial port for --receiver serial (e.g. COM3 on Windows, /dev/ttyUSB0 on Linux)",
    )
    parser.add_argument(
        "--baud",
        type=int,
        help="Serial baud rate (default 500000 for GX6/GX2)",
    )
    parser.add_argument("--vrchat-port", type=int, help="VRChat send port")
    parser.add_argument("--no-camera", action="store_true", help="Run without cameras (OSC passthrough only)")
    parser.add_argument("--no-tray", action="store_true", help="Disable system tray quality meter")
    parser.add_argument("--no-dashboard", action="store_true", help="Disable web dashboard")
    parser.add_argument("--dashboard-port", type=int, default=8765, help="Web dashboard port")
    parser.add_argument("--record", action="store_true", help="Record session to JSONL file")
    parser.add_argument("--profile", action="store_true", help="Enable performance profiling")
    parser.add_argument("--vmc", action="store_true", help="Enable VMC Protocol output")
    parser.add_argument("--vmc-port", type=int, default=39539, help="VMC Protocol port")
    parser.add_argument("--viewer", action="store_true", help="Show 3D skeleton viewer")
    parser.add_argument("--discord", action="store_true", help="Enable Discord Rich Presence")
    parser.add_argument("--api", action="store_true", help="Enable REST API")
    parser.add_argument("--api-port", type=int, default=8766, help="REST API port")
    parser.add_argument("--obs", action="store_true", help="Enable OBS Browser Source overlay")
    parser.add_argument("--obs-port", type=int, default=8767, help="OBS overlay port")
    parser.add_argument("--remap", type=str, help="OSC address remap profile (vrchat/resonite/chilloutvr)")
    parser.add_argument("--bvh", type=str, help="Export BVH file to path")
    parser.add_argument(
        "--smoothing", type=str,
        choices=["default", "anime", "realistic", "dance", "sleep"],
        help="Motion smoothing preset",
    )
    args = parser.parse_args()

    # Load config
    cfg = TrackingConfig.load(args.config) if args.config else TrackingConfig.load()

    # CLI overrides
    if args.cam1 is not None:
        cfg.cam1_index = args.cam1
    if args.cam2 is not None:
        cfg.cam2_index = args.cam2
    if args.cams is not None:
        try:
            parsed_cams = [int(i.strip()) for i in args.cams.split(",") if i.strip()]
        except ValueError:
            logger.error("--cams must be comma-separated integers, got %r", args.cams)
            sys.exit(2)
        if not parsed_cams:
            logger.error("--cams parsed to empty list (got %r) — specify at least one index", args.cams)
            sys.exit(2)
        cfg.cam_indices = parsed_cams
    if args.osc_port is not None:
        cfg.osc_receive_port = args.osc_port
    if args.vrchat_port is not None:
        cfg.osc_send_port = args.vrchat_port
    if args.receiver is not None:
        cfg.receiver_type = args.receiver
    if args.ble_device is not None:
        cfg.ble_device_name_prefix = args.ble_device
    if args.port is not None:
        cfg.serial_port = args.port
    if args.baud is not None:
        cfg.serial_baudrate = args.baud

    # Preflight — fail fast with actionable Japanese messages before we
    # build subsystems and hit a deep traceback.
    issues = run_preflight_checks(cfg, no_camera=args.no_camera)
    for issue in issues:
        print(issue.format(), file=sys.stderr)
    if PreflightIssue.has_errors(issues):
        sys.exit(1)

    # Build components
    camera_config = CameraConfig(
        cam1_index=cfg.cam1_index,
        cam2_index=cfg.cam2_index,
        cam_indices=cfg.cam_indices or None,
        resolution=cfg.camera_resolution,
        target_fps=cfg.target_fps,
        calibration_file=cfg.calibration_file,
        model_path=cfg.model_path,
        model_path_lite=cfg.model_path_lite,
        refine_triangulation=cfg.refine_triangulation,
    )

    camera = CameraTracker(config=camera_config)
    receiver = _build_receiver(cfg)
    sender = OSCSender(
        host=cfg.osc_send_host,
        port=cfg.osc_send_port,
    )

    from .application import EventBus
    bus = EventBus()
    engine = FusionEngine(
        camera=camera, receiver=receiver, sender=sender, config=cfg, event_bus=bus,
    )

    # Optional subsystems
    subs = SubsystemManager()
    tray = dashboard = profiler = gesture = recorder = None
    vmc_sender = viewer = discord = api = bvh = obs_overlay = None

    if not args.no_tray:
        tray = QualityMeter()
        subs.add("tray", tray)
    if not args.no_dashboard:
        dashboard = WebDashboard(port=args.dashboard_port)
        subs.add("dashboard", dashboard)
    if args.profile:
        profiler = PerformanceProfiler()
    if not args.no_camera:
        gesture = GestureDetector()
        gesture.on("recalibrate", lambda: logger.info("Gesture: recalibrate triggered"))
    if args.record:
        from .recorder import TrackingRecorder
        recorder = TrackingRecorder()
        subs.add("recorder", recorder)
    if args.vmc:
        from .vmc_sender import VMCSender
        vmc_sender = VMCSender(port=args.vmc_port)
        subs.add("vmc", vmc_sender)
    if args.viewer:
        from .skeleton_viewer import SkeletonViewer
        viewer = SkeletonViewer()
        subs.add("viewer", viewer)
    if args.discord:
        from .discord_presence import DiscordPresence
        discord = DiscordPresence()
        subs.add("discord", discord)
    if args.api:
        from .rest_api import RestAPI
        api = RestAPI(port=args.api_port)
        subs.add("api", api)
    if args.obs:
        from .obs_overlay import OBSOverlay
        obs_overlay = OBSOverlay(
            port=args.obs_port,
            visible_threshold=cfg.visible_threshold,
            partial_threshold=cfg.partial_threshold,
        )
        subs.add("obs", obs_overlay)
    if args.remap:
        remapper = OSCRemapper(profile_name=args.remap)
        logger.info("OSC remap profile: %s", remapper.profile.name)
    if args.smoothing:
        preset = get_preset(args.smoothing)
        engine.apply_smoothing_preset(preset)
        logger.info("Smoothing preset: %s (rate=%.1f)", preset.name, preset.smooth_rate)

    notifier = NotificationManager()

    if args.bvh:
        from .bvh_exporter import BVHExporter
        bvh = BVHExporter()

    _wire_event_subscribers(
        bus=bus,
        tray=tray,
        dashboard=dashboard,
        recorder=recorder,
        vmc_sender=vmc_sender,
        bvh=bvh,
        viewer=viewer,
        discord=discord,
        api=api,
        obs_overlay=obs_overlay,
        gesture=gesture,
        notifier=notifier,
    )

    def shutdown(sig, frame):
        logger.info("Shutting down...")
        engine.stop()
        subs.stop_all()
        if bvh:
            frames = bvh.export(args.bvh)
            print(f"  BVH exported: {frames} frames to {args.bvh}")
        if profiler:
            print(profiler.report())
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Print startup info
    print("=" * 50)
    print("  OSC Tracking  - IMU x Dual WebCam Fusion")
    print("=" * 50)
    effective_cams = cfg.cam_indices if cfg.cam_indices else [cfg.cam1_index, cfg.cam2_index]
    print(f"  Cameras: {effective_cams} @ {cfg.camera_resolution}")
    print(f"  OSC receive: {cfg.osc_receive_host}:{cfg.osc_receive_port}")
    print(f"  VRChat send: {cfg.osc_send_host}:{cfg.osc_send_port}")
    print(f"  Target FPS: {cfg.target_fps}")
    if args.no_camera:
        print("  Mode: OSC passthrough (no camera)")
    if dashboard:
        print(f"  Dashboard: http://localhost:{args.dashboard_port}")
    if vmc_sender:
        print(f"  VMC output: port {args.vmc_port}")
    if obs_overlay:
        print(f"  OBS overlay: http://localhost:{args.obs_port}")
    if args.remap:
        print(f"  OSC remap: {args.remap}")
    if args.record:
        print("  Recording: enabled")
    if args.bvh:
        print(f"  BVH export: {args.bvh}")
    if args.profile:
        print("  Profiling: enabled")
    print("=" * 50)
    print("  Press Ctrl+C to stop")
    print()

    # Start subsystems
    subs.start_all()

    if not args.no_camera:
        engine.start()
    else:
        receiver.start()
        sender.connect()

    frame_duration = 1.0 / cfg.target_fps
    frame_count = 0
    last_status = time.monotonic()

    try:
        while True:
            loop_start = time.monotonic()

            if profiler:
                profiler.begin_frame()

            # One call does everything: fusion + aggregate update + event
            # publish. All subsystems react through the event bus (wired
            # up earlier via _wire_event_subscribers).
            if not args.no_camera:
                mode = engine.update()
            else:
                mode = TrackingMode.IMU_DISCONNECTED  # Camera-less mode

            if profiler:
                profiler.end_frame()

            frame_count += 1

            # Print status every 2 seconds — this is loop-level telemetry,
            # not a subsystem, so it stays inline.
            if time.monotonic() - last_status > 2.0:
                color = MODE_COLORS.get(mode, "")
                fps = frame_count / (time.monotonic() - last_status)
                imu_status = "OK" if receiver.is_connected else "DISCONNECTED"
                cam_status = "OK" if (not args.no_camera and camera.is_alive) else "OFF"

                print(
                    f"  {color}[{mode.name}]{RESET}  "
                    f"FPS: {fps:.0f}  "
                    f"IMU: {imu_status}  "
                    f"CAM: {cam_status}"
                )

                frame_count = 0
                last_status = time.monotonic()

            elapsed = time.monotonic() - loop_start
            sleep_time = frame_duration - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    except KeyboardInterrupt:
        pass
    finally:
        engine.stop()
        subs.stop_all()
        if bvh:
            frames = bvh.export(args.bvh)
            print(f"  BVH exported: {frames} frames")
        if profiler:
            print(profiler.report())


if __name__ == "__main__":
    main()
