"""Run the tracking pipeline with simulated data.

Usage:
    python -m osc_tracking.tools.simulate [--motion idle|walking|lying|dancing]
"""

import argparse
import signal
import sys
import time

from osc_tracking.complementary_filter import JOINT_NAMES, ComplementaryFilter
from osc_tracking.osc_sender import OSCSender, TrackerOutput
from osc_tracking.simulator import MotionSimulator, SimulationConfig
from osc_tracking.state_machine import ModeConfig, TrackingMode, TrackingStateMachine

MODE_COLORS = {
    TrackingMode.VISIBLE: "\033[92m",
    TrackingMode.PARTIAL_OCCLUSION: "\033[93m",
    TrackingMode.FULL_OCCLUSION: "\033[91m",
    TrackingMode.IMU_DISCONNECTED: "\033[91m",
    TrackingMode.SINGLE_CAM_DEGRADED: "\033[93m",
    TrackingMode.FUTON_MODE: "\033[96m",
}
RESET = "\033[0m"


def main():
    parser = argparse.ArgumentParser(description="Simulate tracking pipeline")
    parser.add_argument("--motion", choices=["idle", "walking", "lying", "dancing"], default="idle")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--noise", type=float, default=0.01)
    parser.add_argument("--occlusion", type=float, default=0.0, help="Occlusion probability (0-1)")
    parser.add_argument("--drift", type=float, default=0.001, help="IMU drift rate (rad/s)")
    parser.add_argument("--send-osc", action="store_true", help="Send output to VRChat via OSC")
    parser.add_argument("--fps", type=int, default=30)
    args = parser.parse_args()

    sim_config = SimulationConfig(
        motion_type=args.motion,
        speed=args.speed,
        noise_level=args.noise,
        occlusion_probability=args.occlusion,
        imu_drift_rate=args.drift,
    )

    simulator = MotionSimulator(sim_config)
    filt = ComplementaryFilter(compass_blend_factor=0.3)
    sm = TrackingStateMachine(config=ModeConfig(hysteresis_sec=0.3))
    sender = OSCSender() if args.send_osc else None

    if sender:
        sender.connect()

    print(f"=== Simulation Mode: {args.motion} ===")
    print(f"  FPS: {args.fps}, Speed: {args.speed}x, Noise: {args.noise}")
    print(f"  Occlusion: {args.occlusion:.0%}, Drift: {args.drift} rad/s")
    print(f"  OSC output: {'ON' if sender else 'OFF'}")
    print("  Press Ctrl+C to stop\n")

    def shutdown(sig, frame):
        if sender:
            sender.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)

    dt = 1.0 / args.fps
    frame_count = 0
    last_status = time.monotonic()
    sm._last_osc_time = time.monotonic()  # Simulate connected IMU

    try:
        while True:
            loop_start = time.monotonic()

            frame = simulator.generate_frame(dt)
            sm.on_imu_received()

            confidences = [conf for _, _, conf in frame.values()]
            avg_conf = sum(confidences) / len(confidences) if confidences else 0
            mode = sm.update(avg_conf, avg_conf, time.monotonic())

            outputs = []
            for name in JOINT_NAMES:
                if name in frame:
                    pos, rot, conf = frame[name]
                    state = filt.update(name, pos, rot, conf, dt)
                    outputs.append(TrackerOutput(
                        position=state.position,
                        rotation=state.rotation,
                        joint_name=name,
                    ))

            if sender:
                sender.send(outputs)

            frame_count += 1
            if time.monotonic() - last_status > 1.0:
                color = MODE_COLORS.get(mode, "")
                fps = frame_count / (time.monotonic() - last_status)
                print(f"  {color}[{mode.name}]{RESET}  FPS: {fps:.0f}  Conf: {avg_conf:.2f}")
                frame_count = 0
                last_status = time.monotonic()

            elapsed = time.monotonic() - loop_start
            sleep_time = dt - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    except KeyboardInterrupt:
        pass
    finally:
        if sender:
            sender.close()


if __name__ == "__main__":
    main()
