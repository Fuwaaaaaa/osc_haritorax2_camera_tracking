"""Entry point for the OSC Tracking system."""

import argparse
import logging
import signal
import sys
import time

from .camera_tracker import CameraConfig, CameraTracker
from .config import TrackingConfig
from .fusion_engine import FusionEngine
from .osc_receiver import OSCReceiver
from .osc_sender import OSCSender
from .state_machine import ModeConfig, TrackingMode

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
}
RESET = "\033[0m"


def main() -> None:
    parser = argparse.ArgumentParser(description="OSC Tracking — HaritoraX2 + Dual WebCam")
    parser.add_argument("--config", type=str, help="Path to config JSON file")
    parser.add_argument("--cam1", type=int, help="Camera 1 index")
    parser.add_argument("--cam2", type=int, help="Camera 2 index")
    parser.add_argument("--osc-port", type=int, help="OSC receive port")
    parser.add_argument("--vrchat-port", type=int, help="VRChat send port")
    parser.add_argument("--no-camera", action="store_true", help="Run without cameras (OSC passthrough only)")
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

    def shutdown(sig, frame):
        logger.info("Shutting down...")
        engine.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Print startup info
    print("=" * 50)
    print("  OSC Tracking — HaritoraX2 + Dual WebCam")
    print("=" * 50)
    print(f"  Cameras: {cfg.cam1_index}, {cfg.cam2_index} @ {cfg.camera_resolution}")
    print(f"  OSC receive: {cfg.osc_receive_host}:{cfg.osc_receive_port}")
    print(f"  VRChat send: {cfg.osc_send_host}:{cfg.osc_send_port}")
    print(f"  Target FPS: {cfg.target_fps}")
    if args.no_camera:
        print("  Mode: OSC passthrough (no camera)")
    print("=" * 50)
    print("  Press Ctrl+C to stop")
    print()

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

            if not args.no_camera:
                mode = engine.update()
            else:
                mode = TrackingMode.IMU_DISCONNECTED  # Camera-less mode

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


if __name__ == "__main__":
    main()
