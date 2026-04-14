"""Performance benchmark tool — measure camera inference latency.

Runs dual-webcam MediaPipe inference for a configurable duration and
reports p50/p95/p99 per-stage latency.  Used to validate that Python
can sustain 30fps+ before committing to the architecture.

Usage:
    python -m osc_tracking.tools.benchmark --cam1 0 --cam2 1 --duration 300
"""

import argparse
import logging
import sys
import time

import numpy as np

logger = logging.getLogger(__name__)


class LatencyCollector:
    """Collects latency samples and computes percentile statistics."""

    def __init__(
        self,
        warn_ms: float = 40.0,
        fail_ms: float = 50.0,
    ):
        self._samples: list[float] = []
        self._warn_ms = warn_ms
        self._fail_ms = fail_ms

    def record(self, ms: float) -> None:
        """Record a latency sample in milliseconds."""
        self._samples.append(ms)

    @property
    def count(self) -> int:
        return len(self._samples)

    def _percentile(self, q: float) -> float:
        if not self._samples:
            return 0.0
        return float(np.percentile(self._samples, q))

    @property
    def p50(self) -> float:
        return self._percentile(50)

    @property
    def p95(self) -> float:
        return self._percentile(95)

    @property
    def p99(self) -> float:
        return self._percentile(99)

    def evaluate(self) -> str:
        """Evaluate p99 against thresholds.

        Returns:
            "PASS" if p99 < warn_ms,
            "WARN" if warn_ms <= p99 < fail_ms,
            "FAIL" if p99 >= fail_ms.
        """
        val = self.p99
        if val < self._warn_ms:
            return "PASS"
        if val < self._fail_ms:
            return "WARN"
        return "FAIL"

    def report(self) -> str:
        """Generate a formatted latency report."""
        lines = [
            f"Latency Report ({self.count} samples)",
            f"  p50:  {self.p50:7.2f} ms",
            f"  p95:  {self.p95:7.2f} ms",
            f"  p99:  {self.p99:7.2f} ms",
            f"  Result: {self.evaluate()}",
        ]
        return "\n".join(lines)


def _run_benchmark(cam1_id: int, cam2_id: int, duration_sec: int) -> None:
    """Run the benchmark loop (requires cameras).

    Uses MediaPipe Pose Landmarker Tasks API (NOT legacy BlazePose).
    """
    try:
        import cv2
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions
        from mediapipe.tasks.python.vision import (
            PoseLandmarker,
            PoseLandmarkerOptions,
            RunningMode,
        )
    except ImportError as exc:
        logger.error("Missing dependency: %s", exc)
        sys.exit(1)

    from osc_tracking.camera_tracker import CameraConfig, MODEL_PATH_DEFAULT

    from pathlib import Path
    model_path = MODEL_PATH_DEFAULT
    if not Path(model_path).exists():
        logger.error(
            "Model not found at %s. Run: python -m osc_tracking.tools.download_model",
            model_path,
        )
        sys.exit(1)

    caps = []
    for cam_id in (cam1_id, cam2_id):
        cap = cv2.VideoCapture(cam_id)
        if not cap.isOpened():
            logger.error("Cannot open camera %d", cam_id)
            sys.exit(1)
        caps.append(cap)

    collector = LatencyCollector()
    landmarkers = []
    for _ in range(2):
        options = PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=model_path),
            running_mode=RunningMode.VIDEO,
            num_poses=1,
        )
        landmarkers.append(PoseLandmarker.create_from_options(options))

    print(f"Running benchmark for {duration_sec}s on cameras {cam1_id}, {cam2_id}...")
    print(f"Model: {model_path} (Pose Landmarker Tasks API)")
    start = time.monotonic()
    frame_ts = 0

    try:
        while time.monotonic() - start < duration_sec:
            frame_start = time.perf_counter()

            for cap, landmarker in zip(caps, landmarkers):
                ret, frame = cap.read()
                if not ret:
                    continue
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                landmarker.detect_for_video(mp_image, frame_ts)

            frame_ts += 33  # ~30fps in milliseconds
            elapsed_ms = (time.perf_counter() - frame_start) * 1000
            collector.record(elapsed_ms)
    except KeyboardInterrupt:
        print("\nBenchmark interrupted.")
    finally:
        for cap in caps:
            cap.release()
        for lm in landmarkers:
            lm.close()

    print()
    print(collector.report())

    if collector.evaluate() == "FAIL":
        print("\nFAILED: p99 > 50ms. Architecture may need rethinking.")
        print("Contingency options:")
        print("  1. ONNX Runtime (replace MediaPipe Python)")
        print("  2. GPU subprocess (dedicated inference process)")
        print("  3. Single camera (halve inference cost)")
        sys.exit(1)
    elif collector.evaluate() == "WARN":
        print("\nWARNING: p99 40-50ms. Marginal — monitor closely.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark camera inference latency",
    )
    parser.add_argument("--cam1", type=int, default=0, help="Camera 1 ID")
    parser.add_argument("--cam2", type=int, default=1, help="Camera 2 ID")
    parser.add_argument(
        "--duration", type=int, default=300, help="Duration in seconds (default 300)"
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    _run_benchmark(args.cam1, args.cam2, args.duration)


if __name__ == "__main__":
    main()
