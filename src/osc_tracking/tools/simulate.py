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
    parser.add_argument("--no-network", action="store_true", help="Force-disable all network I/O (ignores --send-osc)")
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--duration", type=float, default=0.0, help="Stop after N seconds (0 = run until Ctrl-C)")
    parser.add_argument(
        "--verify-modes",
        action="store_true",
        help="Scripted E2E: cycle through scenarios that force VISIBLE / OCCLUSION / "
             "IMU_DISCONNECTED transitions, then exit 0 if each was observed, 1 otherwise. "
             "Designed as a CI smoke gate — implies --no-network.",
    )
    args = parser.parse_args()

    if args.verify_modes:
        return _run_verify_modes(args)

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
    # --no-network overrides --send-osc so CI can run without needing
    # localhost UDP to be available.
    sender = OSCSender() if (args.send_osc and not args.no_network) else None

    if sender:
        sender.connect()

    end_time = time.monotonic() + args.duration if args.duration > 0 else None

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

            if end_time is not None and time.monotonic() >= end_time:
                break

    except KeyboardInterrupt:
        pass
    finally:
        if sender:
            sender.close()


def _run_verify_modes(args) -> int:
    """CI smoke gate: drive the pipeline through scripted scenarios and
    assert we observed each expected tracking mode.

    Implies ``--no-network`` so the gate stays runnable on any CI runner.
    Exits 0 when the required mode set is observed, 1 otherwise.
    """
    from osc_tracking.simulator import MotionSimulator, SimulationConfig

    phases = [
        # (label, duration_sec, occlusion_prob, imu_connected)
        ("VISIBLE warmup", 2.0, 0.0, True),
        ("PARTIAL occlusion", 2.0, 0.6, True),
        ("FULL occlusion", 2.0, 1.0, True),
        ("IMU disconnected", 2.0, 0.0, False),
        ("Recovery", 2.0, 0.0, True),
    ]
    total_budget = args.duration if args.duration > 0 else sum(p[1] for p in phases)
    scale = total_budget / sum(p[1] for p in phases)

    # Short timeouts so the IMU_DISCONNECTED phase actually triggers
    # within a ~10s budget on CI.
    sm = TrackingStateMachine(config=ModeConfig(
        hysteresis_sec=0.1,
        osc_timeout_sec=0.3,
    ))
    sim = MotionSimulator(SimulationConfig(
        motion_type=args.motion,
        speed=args.speed,
        noise_level=args.noise,
        imu_drift_rate=args.drift,
    ))

    dt = 1.0 / max(args.fps, 1)
    observed: set[TrackingMode] = set()

    print("=== E2E smoke: --verify-modes ===")
    print(f"  Total budget: {total_budget:.1f}s across {len(phases)} phases\n")

    for label, base_dur, occlusion, imu_on in phases:
        phase_dur = base_dur * scale
        phase_end = time.monotonic() + phase_dur
        sim.config.occlusion_probability = occlusion
        while time.monotonic() < phase_end:
            frame = sim.generate_frame(dt)
            if imu_on:
                sm.on_imu_received()
            confidences = [c for _, _, c in frame.values()]
            avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
            mode = sm.update(avg_conf, avg_conf, time.monotonic())
            observed.add(mode)
            time.sleep(dt)
        print(f"  [{label}] last mode={mode.name}, observed so far={sorted(m.name for m in observed)}")

    required_any_of = [
        {TrackingMode.VISIBLE},
        {TrackingMode.PARTIAL_OCCLUSION, TrackingMode.FULL_OCCLUSION},
        {TrackingMode.IMU_DISCONNECTED, TrackingMode.FULL_OCCLUSION},
    ]
    missing = [
        f"one of {{{', '.join(sorted(m.name for m in group))}}}"
        for group in required_any_of
        if not (group & observed)
    ]
    if missing:
        print("\nFAIL: did not observe required modes:")
        for m in missing:
            print(f"  - {m}")
        return 1

    print("\nPASS: all required modes observed.")
    return 0


if __name__ == "__main__":
    rc = main()
    sys.exit(int(rc) if isinstance(rc, int) else 0)
