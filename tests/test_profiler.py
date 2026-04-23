"""Tests for the PerformanceProfiler.

Uses ``time.perf_counter`` mocking so assertions are deterministic
rather than depending on wall-clock.
"""

from __future__ import annotations

from itertools import count
from unittest.mock import patch

import pytest

from osc_tracking.profiler import PerformanceProfiler, TimingStats

# ---------- TimingStats ----------

def test_timing_stats_defaults():
    s = TimingStats()
    assert s.count == 0
    assert s.total_ms == 0.0
    assert s.avg_ms == 0.0
    assert s.max_ms == 0.0
    assert s.min_ms == float("inf")


def test_timing_stats_record_updates_aggregates():
    s = TimingStats()
    s.record(10.0)
    s.record(20.0)
    s.record(5.0)
    assert s.count == 3
    assert s.total_ms == 35.0
    assert s.avg_ms == pytest.approx(35.0 / 3)
    assert s.min_ms == 5.0
    assert s.max_ms == 20.0


def test_timing_stats_avg_with_zero_count_is_zero():
    """Should not divide by zero."""
    s = TimingStats()
    assert s.avg_ms == 0.0


# ---------- PerformanceProfiler ----------

@pytest.fixture
def fake_perf():
    """Yield a profiler where time.perf_counter advances 1.0s per call.
    Starts at 1.0 so ``begin_frame`` sees a truthy timestamp (the guard
    in ``end_frame`` checks ``> 0``)."""
    ticker = count(start=1, step=1.0)
    with patch(
        "osc_tracking.profiler.time.perf_counter",
        side_effect=lambda: next(ticker),
    ):
        yield PerformanceProfiler()


def test_begin_end_records_stage(fake_perf):
    fake_perf.begin("filter")  # t=0
    fake_perf.end("filter")    # t=1, elapsed = 1000ms
    stats = fake_perf.get_stats("filter")
    assert stats.count == 1
    assert stats.total_ms == pytest.approx(1000.0)


def test_multiple_stages_tracked_independently(fake_perf):
    fake_perf.begin("a")  # 0
    fake_perf.end("a")    # 1 -> 1000ms
    fake_perf.begin("b")  # 2
    fake_perf.end("b")    # 3 -> 1000ms
    assert fake_perf.get_stats("a").count == 1
    assert fake_perf.get_stats("b").count == 1


def test_end_without_begin_is_noop(fake_perf):
    """Calling end() on a stage never started must not crash."""
    fake_perf.end("never_started")
    assert fake_perf.get_stats("never_started").count == 0


def test_begin_frame_end_frame_records_frame_time(fake_perf):
    fake_perf.begin_frame()  # 0
    fake_perf.end_frame()    # 1 -> 1000ms
    assert fake_perf._frame_stats.count == 1
    assert fake_perf._frame_stats.total_ms == pytest.approx(1000.0)


def test_end_frame_without_begin_is_noop(fake_perf):
    """End_frame before begin_frame (self._frame_start == 0) does nothing."""
    fake_perf.end_frame()
    assert fake_perf._frame_stats.count == 0


def test_reset_clears_stage_and_frame_stats(fake_perf):
    fake_perf.begin("x")
    fake_perf.end("x")
    fake_perf.begin_frame()
    fake_perf.end_frame()
    fake_perf.reset()
    assert len(fake_perf._stats) == 0
    assert fake_perf._frame_stats.count == 0


def test_report_lists_recorded_stages(fake_perf):
    fake_perf.begin("stage_a")
    fake_perf.end("stage_a")
    fake_perf.begin("stage_b")
    fake_perf.end("stage_b")
    report = fake_perf.report()
    assert "Performance Report" in report
    assert "stage_a" in report
    assert "stage_b" in report


def test_report_includes_total_frame_row(fake_perf):
    fake_perf.begin_frame()
    fake_perf.end_frame()
    report = fake_perf.report()
    assert "TOTAL FRAME" in report
    assert "Effective FPS" in report


def test_report_handles_no_frame_data():
    """Report before any frame data should not crash and should not
    show an FPS line (avoiding div-by-zero)."""
    p = PerformanceProfiler()
    report = p.report()
    assert "TOTAL FRAME" in report
    assert "Effective FPS" not in report
