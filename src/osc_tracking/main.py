"""Entry point for the OSC Tracking system."""

import argparse
import logging
import signal
import sys
import time

from scipy.spatial.transform import Rotation

from .camera_tracker import CameraConfig, CameraTracker
from .config import TrackingConfig
from .fusion_engine import FusionEngine
from .gesture_detector import GestureDetector
from .motion_smoothing import get_preset
from .notifications import NotificationManager
from .osc_receiver import OSCReceiver
from .osc_remapper import OSCRemapper
from .osc_sender import OSCSender
from .profiler import PerformanceProfiler
from .quality_meter import QualityLevel, QualityMeter
from .state_machine import ModeConfig, TrackingMode
from .web_dashboard import WebDashboard

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

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


def main() -> None:
    parser = argparse.ArgumentParser(description="OSC Tracking  - HaritoraX2 + Dual WebCam")
    parser.add_argument("--config", type=str, help="Path to config JSON file")
    parser.add_argument("--cam1", type=int, help="Camera 1 index")
    parser.add_argument("--cam2", type=int, help="Camera 2 index")
    parser.add_argument("--osc-port", type=int, help="OSC receive port")
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
    if args.osc_port is not None:
        cfg.osc_receive_port = args.osc_port
    if args.vrchat_port is not None:
        cfg.osc_send_port = args.vrchat_port

    # Build components
    camera_config = CameraConfig(
        cam1_index=cfg.cam1_index,
        cam2_index=cfg.cam2_index,
        resolution=cfg.camera_resolution,
        target_fps=cfg.target_fps,
        calibration_file=cfg.calibration_file,
        model_path=cfg.model_path,
        model_path_lite=cfg.model_path_lite,
    )

    camera = CameraTracker(config=camera_config)
    receiver = OSCReceiver(
        host=cfg.osc_receive_host,
        port=cfg.osc_receive_port,
    )
    sender = OSCSender(
        host=cfg.osc_send_host,
        port=cfg.osc_send_port,
    )

    # Apply state machine config
    mode_config = ModeConfig(
        visible_threshold=cfg.visible_threshold,
        partial_threshold=cfg.partial_threshold,
        osc_timeout_sec=cfg.osc_timeout_sec,
        hysteresis_sec=cfg.hysteresis_sec,
    )

    engine = FusionEngine(camera=camera, receiver=receiver, sender=sender)
    engine.state_machine.config = mode_config

    # Optional subsystems
    tray: QualityMeter | None = None
    dashboard: WebDashboard | None = None
    profiler: PerformanceProfiler | None = None
    gesture: GestureDetector | None = None
    recorder = None

    if not args.no_tray:
        tray = QualityMeter()
    if not args.no_dashboard:
        dashboard = WebDashboard(port=args.dashboard_port)
    if args.profile:
        profiler = PerformanceProfiler()
    if not args.no_camera:
        gesture = GestureDetector()
        gesture.on("recalibrate", lambda: logger.info("Gesture: recalibrate triggered"))
    if args.record:
        from .recorder import TrackingRecorder
        recorder = TrackingRecorder()

    # VMC Protocol output
    vmc_sender = None
    if args.vmc:
        from .vmc_sender import VMCSender
        vmc_sender = VMCSender(port=args.vmc_port)

    # 3D skeleton viewer
    viewer = None
    if args.viewer:
        from .skeleton_viewer import SkeletonViewer
        viewer = SkeletonViewer()

    # Discord Rich Presence
    discord = None
    if args.discord:
        from .discord_presence import DiscordPresence
        discord = DiscordPresence()

    # REST API
    api = None
    if args.api:
        from .rest_api import RestAPI
        api = RestAPI(port=args.api_port)

    # OSC address remapper
    if args.remap:
        remapper = OSCRemapper(profile_name=args.remap)
        logger.info("OSC remap profile: %s", remapper.profile.name)

    # Motion smoothing preset
    if args.smoothing:
        preset = get_preset(args.smoothing)
        engine.filter.SMOOTH_RATE = preset.smooth_rate
        engine.filter.DRIFT_VELOCITY_THRESHOLD = preset.noise_threshold
        logger.info("Smoothing preset: %s (rate=%.1f)", preset.name, preset.smooth_rate)

    # Notifications (always on)
    notifier = NotificationManager()

    # BVH exporter
    bvh = None
    if args.bvh:
        from .bvh_exporter import BVHExporter
        bvh = BVHExporter()

    def shutdown(sig, frame):
        logger.info("Shutting down...")
        engine.stop()
        if tray:
            tray.stop()
        if dashboard:
            dashboard.stop()
        if recorder:
            count = recorder.stop()
            print(f"  Recording saved: {count} frames")
        if bvh:
            frames = bvh.export(args.bvh)
            print(f"  BVH exported: {frames} frames to {args.bvh}")
        if viewer:
            viewer.stop()
        if api:
            api.stop()
        if vmc_sender:
            vmc_sender.close()
        if discord:
            discord.stop()
        if profiler:
            print(profiler.report())
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Print startup info
    print("=" * 50)
    print("  OSC Tracking  - HaritoraX2 + Dual WebCam")
    print("=" * 50)
    print(f"  Cameras: {cfg.cam1_index}, {cfg.cam2_index} @ {cfg.camera_resolution}")
    print(f"  OSC receive: {cfg.osc_receive_host}:{cfg.osc_receive_port}")
    print(f"  VRChat send: {cfg.osc_send_host}:{cfg.osc_send_port}")
    print(f"  Target FPS: {cfg.target_fps}")
    if args.no_camera:
        print("  Mode: OSC passthrough (no camera)")
    if dashboard:
        print(f"  Dashboard: http://localhost:{args.dashboard_port}")
    if vmc_sender:
        print(f"  VMC output: port {args.vmc_port}")
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
    if tray:
        tray.start()
    if dashboard:
        dashboard.start()
    if recorder:
        recorder.start()
    if vmc_sender:
        vmc_sender.connect()
    if viewer:
        viewer.start()
    if discord:
        discord.start()
    if api:
        api.start()

    if not args.no_camera:
        engine.start()
    else:
        receiver.start()
        sender.connect()

    frame_duration = 1.0 / cfg.target_fps
    frame_count = 0
    last_status = time.monotonic()
    prev_mode = TrackingMode.VISIBLE

    try:
        while True:
            loop_start = time.monotonic()

            if profiler:
                profiler.begin_frame()

            if not args.no_camera:
                mode = engine.update()
            else:
                mode = TrackingMode.IMU_DISCONNECTED  # Camera-less mode

            # Read camera data ONCE per frame (avoid repeated Lock + copy)
            cj = camera.read_joints() if not args.no_camera else None
            avg_conf = 0.0
            if cj:
                confs = [c for _, c in cj.values()]
                avg_conf = sum(confs) / len(confs) if confs else 0.0

            fps_now = frame_count / max(time.monotonic() - last_status, 0.001)

            # Helper: get rotation for a joint, fallback to identity
            def _get_rot(name: str):
                rot = receiver.get_bone_rotation(name)
                return rot if rot is not None else Rotation.identity()

            # Gesture detection
            if gesture and cj:
                joint_positions = {name: pos for name, (pos, _) in cj.items()}
                detected = gesture.update(joint_positions)
                if detected:
                    logger.info("Gesture detected: %s", detected)

            # Tray icon
            if tray:
                if mode == TrackingMode.VISIBLE:
                    level = QualityLevel.GOOD
                elif mode in (TrackingMode.PARTIAL_OCCLUSION, TrackingMode.SINGLE_CAM_DEGRADED):
                    level = QualityLevel.WARNING
                elif mode in (TrackingMode.FULL_OCCLUSION, TrackingMode.IMU_DISCONNECTED):
                    level = QualityLevel.ERROR
                else:
                    level = QualityLevel.OFFLINE
                tray.update(level, mode.name, fps_now)

            # Dashboard
            if dashboard:
                joint_data = {name: {"conf": c} for name, (_, c) in cj.items()} if cj else {}
                dashboard.update(mode.name, fps_now, avg_conf, joint_data)

            # Recorder
            if recorder and cj:
                rec_data = {name: (pos, _get_rot(name), conf) for name, (pos, conf) in cj.items()}
                recorder.record_frame(rec_data, mode.name)

            # VMC Protocol
            if vmc_sender and cj:
                vmc_data = {name: (pos, _get_rot(name)) for name, (pos, _) in cj.items()}
                vmc_sender.send_frame(vmc_data)

            # BVH recording
            if bvh and cj:
                bvh_data = {name: (pos, _get_rot(name)) for name, (pos, _) in cj.items()}
                bvh.add_frame(bvh_data)

            # Skeleton viewer
            if viewer and cj:
                viewer.update({name: pos for name, (pos, _) in cj.items()})

            # Discord presence
            if discord:
                discord.update(mode.name, fps_now)

            # REST API
            if api:
                joint_data = {name: {"conf": c} for name, (_, c) in cj.items()} if cj else {}
                api.update(mode.name, fps_now, joint_data)

            # Notifications  - only on mode change
            if mode != prev_mode:
                if mode == TrackingMode.IMU_DISCONNECTED:
                    notifier.notify_disconnect()
                elif mode == TrackingMode.FULL_OCCLUSION:
                    notifier.notify_camera_lost(0)
                elif mode == TrackingMode.VISIBLE and prev_mode == TrackingMode.IMU_DISCONNECTED:
                    notifier.notify_reconnect()
                elif mode == TrackingMode.VISIBLE and prev_mode == TrackingMode.FULL_OCCLUSION:
                    notifier.notify_camera_recovered(0)
                prev_mode = mode

            if profiler:
                profiler.end_frame()

            frame_count += 1

            # Print status every 2 seconds
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
        if tray:
            tray.stop()
        if dashboard:
            dashboard.stop()
        if recorder:
            recorder.stop()
        if bvh:
            frames = bvh.export(args.bvh)
            print(f"  BVH exported: {frames} frames")
        if viewer:
            viewer.stop()
        if api:
            api.stop()
        if vmc_sender:
            vmc_sender.close()
        if discord:
            discord.stop()
        if profiler:
            print(profiler.report())


if __name__ == "__main__":
    main()
