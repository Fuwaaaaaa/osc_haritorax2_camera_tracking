"""Performance profiler — measure per-module processing time.

Wraps each pipeline stage to track execution time and identify bottlenecks.
"""

import logging
import time
from collections import defaultdict
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TimingStats:
    count: int = 0
    total_ms: float = 0.0
    min_ms: float = float("inf")
    max_ms: float = 0.0

    @property
    def avg_ms(self) -> float:
        return self.total_ms / max(self.count, 1)

    def record(self, ms: float) -> None:
        self.count += 1
        self.total_ms += ms
        self.min_ms = min(self.min_ms, ms)
        self.max_ms = max(self.max_ms, ms)


class PerformanceProfiler:
    """Tracks per-stage execution time for the tracking pipeline."""

    def __init__(self):
        self._stats: dict[str, TimingStats] = defaultdict(TimingStats)
        self._active: dict[str, float] = {}
        self._frame_start: float = 0.0
        self._frame_stats = TimingStats()

    def begin_frame(self) -> None:
        self._frame_start = time.perf_counter()

    def end_frame(self) -> None:
        if self._frame_start > 0:
            elapsed = (time.perf_counter() - self._frame_start) * 1000
            self._frame_stats.record(elapsed)

    def begin(self, stage: str) -> None:
        self._active[stage] = time.perf_counter()

    def end(self, stage: str) -> None:
        start = self._active.pop(stage, None)
        if start is not None:
            elapsed = (time.perf_counter() - start) * 1000
            self._stats[stage].record(elapsed)

    def report(self) -> str:
        """Generate a formatted performance report."""
        lines = ["=== Performance Report ==="]
        lines.append(f"{'Stage':<25} {'Avg':>8} {'Min':>8} {'Max':>8} {'Count':>8}")
        lines.append("-" * 60)

        for name, stats in sorted(self._stats.items()):
            lines.append(
                f"{name:<25} {stats.avg_ms:>7.2f}ms {stats.min_ms:>7.2f}ms "
                f"{stats.max_ms:>7.2f}ms {stats.count:>8}"
            )

        lines.append("-" * 60)
        fs = self._frame_stats
        lines.append(
            f"{'TOTAL FRAME':<25} {fs.avg_ms:>7.2f}ms {fs.min_ms:>7.2f}ms "
            f"{fs.max_ms:>7.2f}ms {fs.count:>8}"
        )
        if fs.avg_ms > 0:
            lines.append(f"Effective FPS: {1000 / fs.avg_ms:.1f}")

        return "\n".join(lines)

    def reset(self) -> None:
        self._stats.clear()
        self._frame_stats = TimingStats()

    def get_stats(self, stage: str) -> TimingStats:
        return self._stats[stage]
