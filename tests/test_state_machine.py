"""Tests for the tracking state machine."""

import time

import pytest

from osc_tracking.state_machine import ModeConfig, TrackingMode, TrackingStateMachine


@pytest.fixture
def sm():
    config = ModeConfig(hysteresis_sec=0.0)  # Disable hysteresis for unit tests
    machine = TrackingStateMachine(config=config)
    machine._last_osc_time = time.monotonic()  # Simulate connected IMU
    return machine


@pytest.fixture
def sm_with_hysteresis():
    config = ModeConfig(hysteresis_sec=0.5)
    machine = TrackingStateMachine(config=config)
    machine._last_osc_time = time.monotonic()
    return machine


class TestVisibleMode:
    def test_high_confidence_stays_visible(self, sm):
        mode = sm.update(0.9, 0.8)
        assert mode == TrackingMode.VISIBLE

    def test_both_cameras_high(self, sm):
        mode = sm.update(1.0, 1.0)
        assert mode == TrackingMode.VISIBLE


class TestPartialOcclusion:
    def test_medium_confidence_transitions(self, sm):
        mode = sm.update(0.5, 0.5)
        assert mode == TrackingMode.PARTIAL_OCCLUSION

    def test_boundary_at_07(self, sm):
        """Confidence exactly at 0.7 boundary (average 0.7 → Visible)."""
        mode = sm.update(0.7, 0.7)
        assert mode == TrackingMode.VISIBLE

    def test_just_below_07(self, sm):
        mode = sm.update(0.69, 0.69)
        assert mode == TrackingMode.PARTIAL_OCCLUSION


class TestFullOcclusion:
    def test_low_confidence(self, sm):
        mode = sm.update(0.1, 0.1)
        assert mode == TrackingMode.FULL_OCCLUSION

    def test_zero_confidence(self, sm):
        mode = sm.update(0.0, 0.0)
        assert mode == TrackingMode.FULL_OCCLUSION

    def test_boundary_at_03(self, sm):
        """Average exactly 0.3 → Partial, not Full."""
        mode = sm.update(0.3, 0.3)
        assert mode == TrackingMode.PARTIAL_OCCLUSION


class TestIMUDisconnection:
    def test_osc_timeout_triggers_disconnect(self, sm):
        sm._last_osc_time = time.monotonic() - 2.0  # 2s ago
        mode = sm.update(0.9, 0.9)
        assert mode == TrackingMode.IMU_DISCONNECTED

    def test_reconnection_triggers_resync(self, sm):
        sm._last_osc_time = time.monotonic() - 2.0
        sm.update(0.9, 0.9)
        assert sm.mode == TrackingMode.IMU_DISCONNECTED

        sm.on_osc_received()
        assert sm.is_resyncing

    def test_resync_expires(self, sm):
        sm._resync_start = time.monotonic() - 2.0  # Resync started 2s ago
        assert not sm.is_resyncing


class TestSingleCameraDegradation:
    def test_one_camera_low_other_high(self, sm):
        mode = sm.update(0.9, 0.1)
        assert mode == TrackingMode.SINGLE_CAM_DEGRADED

    def test_both_cameras_similar_not_degraded(self, sm):
        mode = sm.update(0.5, 0.5)
        assert mode != TrackingMode.SINGLE_CAM_DEGRADED


class TestBothCamerasLost:
    def test_both_cameras_zero_goes_full_occlusion(self, sm):
        mode = sm.update(0.0, 0.0)
        assert mode == TrackingMode.FULL_OCCLUSION

    def test_transition_from_visible_to_full(self, sm):
        sm.update(0.9, 0.9)
        assert sm.mode == TrackingMode.VISIBLE
        mode = sm.update(0.0, 0.0)
        assert mode == TrackingMode.FULL_OCCLUSION

    def test_both_cameras_zero_bypasses_hysteresis(self, sm):
        """Both cameras at 0.0 should immediately enter FULL_OCCLUSION."""
        sm.config.hysteresis_sec = 10.0  # Long hysteresis
        sm.update(0.9, 0.9)  # Start in VISIBLE
        assert sm.mode == TrackingMode.VISIBLE

        mode = sm.update(0.0, 0.0)
        assert mode == TrackingMode.FULL_OCCLUSION  # Immediate, no hysteresis

    def test_both_cameras_near_zero_bypasses_hysteresis(self, sm):
        """Both cameras below 0.05 should bypass hysteresis."""
        sm.config.hysteresis_sec = 10.0
        sm.update(0.9, 0.9)
        mode = sm.update(0.02, 0.03)
        assert mode == TrackingMode.FULL_OCCLUSION

    def test_single_cam_degraded_to_both_lost(self, sm):
        """From SINGLE_CAM_DEGRADED, if remaining camera also dies, go to FULL."""
        sm.config.hysteresis_sec = 0.0
        sm.update(0.8, 0.1)  # One camera bad → SINGLE_CAM_DEGRADED
        assert sm.mode == TrackingMode.SINGLE_CAM_DEGRADED

        mode = sm.update(0.0, 0.0)  # Both lost
        assert mode == TrackingMode.FULL_OCCLUSION


class TestHysteresis:
    def test_rapid_mode_switch_prevented(self, sm_with_hysteresis):
        now = time.monotonic()
        sm_with_hysteresis.update(0.9, 0.9, now=now)
        assert sm_with_hysteresis.mode == TrackingMode.VISIBLE

        # Drop confidence — should NOT immediately switch
        sm_with_hysteresis.update(0.1, 0.1, now=now + 0.1)
        assert sm_with_hysteresis.mode == TrackingMode.VISIBLE  # Still visible

        # After hysteresis period
        sm_with_hysteresis.update(0.1, 0.1, now=now + 0.7)
        assert sm_with_hysteresis.mode == TrackingMode.FULL_OCCLUSION


class TestSmoothRecovery:
    def test_full_to_visible_recovery(self, sm):
        sm.update(0.0, 0.0)
        assert sm.mode == TrackingMode.FULL_OCCLUSION

        mode = sm.update(0.9, 0.9)
        assert mode == TrackingMode.VISIBLE
