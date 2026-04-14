"""Tests for the benchmark latency collector."""

import pytest

from osc_tracking.tools.benchmark import LatencyCollector


class TestLatencyCollector:
    """Test LatencyCollector percentile computation and threshold evaluation."""

    def test_record_and_count(self):
        lc = LatencyCollector()
        lc.record(10.0)
        lc.record(20.0)
        lc.record(30.0)
        assert lc.count == 3

    def test_p50_simple(self):
        lc = LatencyCollector()
        for v in [10, 20, 30, 40, 50]:
            lc.record(v)
        assert lc.p50 == pytest.approx(30.0, abs=1)

    def test_p95_simple(self):
        lc = LatencyCollector()
        for v in range(1, 101):
            lc.record(float(v))
        assert lc.p95 == pytest.approx(95.5, abs=1)

    def test_p99_simple(self):
        lc = LatencyCollector()
        for v in range(1, 101):
            lc.record(float(v))
        assert lc.p99 == pytest.approx(99.5, abs=1)

    def test_empty_returns_zero(self):
        lc = LatencyCollector()
        assert lc.p50 == 0.0
        assert lc.p95 == 0.0
        assert lc.p99 == 0.0
        assert lc.count == 0

    def test_single_sample(self):
        lc = LatencyCollector()
        lc.record(42.0)
        assert lc.p50 == 42.0
        assert lc.p95 == 42.0
        assert lc.p99 == 42.0

    def test_negative_values_recorded(self):
        lc = LatencyCollector()
        lc.record(-5.0)
        lc.record(10.0)
        assert lc.count == 2
        assert lc.p50 == pytest.approx(2.5, abs=1)

    def test_threshold_pass(self):
        lc = LatencyCollector()
        for _ in range(100):
            lc.record(20.0)  # p99 = 20ms < 40ms
        assert lc.evaluate() == "PASS"

    def test_threshold_warn(self):
        lc = LatencyCollector()
        for _ in range(100):
            lc.record(45.0)  # p99 = 45ms, 40-50 range
        assert lc.evaluate() == "WARN"

    def test_threshold_fail(self):
        lc = LatencyCollector()
        for _ in range(100):
            lc.record(60.0)  # p99 = 60ms > 50ms
        assert lc.evaluate() == "FAIL"

    def test_threshold_boundary_40(self):
        lc = LatencyCollector()
        for _ in range(100):
            lc.record(40.0)  # p99 = 40ms exactly
        assert lc.evaluate() == "WARN"

    def test_threshold_boundary_50(self):
        lc = LatencyCollector()
        for _ in range(100):
            lc.record(50.0)  # p99 = 50ms exactly
        assert lc.evaluate() == "FAIL"

    def test_custom_thresholds(self):
        lc = LatencyCollector(warn_ms=30.0, fail_ms=40.0)
        for _ in range(100):
            lc.record(35.0)
        assert lc.evaluate() == "WARN"

    def test_report_format(self):
        lc = LatencyCollector()
        for v in range(1, 51):
            lc.record(float(v))
        report = lc.report()
        assert "p50" in report
        assert "p95" in report
        assert "p99" in report
        assert "samples" in report.lower() or "count" in report.lower()
