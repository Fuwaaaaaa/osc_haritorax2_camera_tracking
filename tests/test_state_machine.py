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

        sm.on_imu_received()
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


class TestFutonMode:
    """Tests for FUTON_MODE (lying down detection)."""

    @pytest.fixture
    def sm_futon(self):
        config = ModeConfig(
            hysteresis_sec=0.0,
            futon_pitch_threshold=60.0,
            futon_exit_threshold=30.0,
            futon_dwell_time_sec=0.0,  # Disable dwell for unit tests
        )
        machine = TrackingStateMachine(config=config)
        machine._last_osc_time = time.monotonic()
        return machine

    def test_high_pitch_enters_futon_mode(self, sm_futon):
        """Pitch > 60 degrees should trigger FUTON_MODE."""
        sm_futon.on_imu_pitch(70.0)
        mode = sm_futon.update(0.9, 0.9)
        assert mode == TrackingMode.FUTON_MODE

    def test_upright_exits_futon_mode(self, sm_futon):
        """Pitch < 30 degrees should exit FUTON_MODE."""
        sm_futon.on_imu_pitch(70.0)
        sm_futon.update(0.9, 0.9)
        assert sm_futon.mode == TrackingMode.FUTON_MODE

        sm_futon.on_imu_pitch(20.0)
        mode = sm_futon.update(0.9, 0.9)
        assert mode != TrackingMode.FUTON_MODE

    def test_pitch_in_deadband_stays_in_mode(self, sm_futon):
        """Pitch between 30 and 60 should not change mode (hysteresis band)."""
        sm_futon.on_imu_pitch(70.0)
        sm_futon.update(0.9, 0.9)
        assert sm_futon.mode == TrackingMode.FUTON_MODE

        sm_futon.on_imu_pitch(45.0)  # In deadband
        mode = sm_futon.update(0.9, 0.9)
        assert mode == TrackingMode.FUTON_MODE  # Should stay

    def test_imu_disconnected_overrides_futon(self, sm_futon):
        """IMU_DISCONNECTED has higher priority than FUTON_MODE."""
        sm_futon.on_imu_pitch(70.0)
        sm_futon.update(0.9, 0.9)
        assert sm_futon.mode == TrackingMode.FUTON_MODE

        # Simulate OSC timeout
        now = time.monotonic()
        sm_futon._last_osc_time = now - 2.0
        mode = sm_futon.update(0.9, 0.9, now=now)
        assert mode == TrackingMode.IMU_DISCONNECTED

    def test_nan_pitch_does_not_trigger_futon(self, sm_futon):
        """NaN pitch should be ignored — never trigger FUTON_MODE."""
        sm_futon.on_imu_pitch(float("nan"))
        mode = sm_futon.update(0.9, 0.9)
        assert mode != TrackingMode.FUTON_MODE

    def test_inf_pitch_does_not_trigger_futon(self, sm_futon):
        """Infinite pitch should be ignored."""
        sm_futon.on_imu_pitch(float("inf"))
        mode = sm_futon.update(0.9, 0.9)
        assert mode != TrackingMode.FUTON_MODE

    def test_dwell_time_prevents_flapping(self, monkeypatch):
        """Mode should not transition until dwell time has elapsed."""
        config = ModeConfig(
            hysteresis_sec=0.0,
            futon_pitch_threshold=60.0,
            futon_exit_threshold=30.0,
            futon_dwell_time_sec=0.5,
        )
        sm = TrackingStateMachine(config=config)

        fake_time = [100.0]
        monkeypatch.setattr(time, "monotonic", lambda: fake_time[0])
        sm._last_osc_time = fake_time[0]

        sm.on_imu_pitch(70.0)
        mode = sm.update(0.9, 0.9, now=fake_time[0])
        # Should NOT yet be in FUTON_MODE (dwell not elapsed)
        assert mode != TrackingMode.FUTON_MODE

        # Advance past dwell time
        fake_time[0] = 100.6
        sm.on_imu_pitch(70.0)
        mode = sm.update(0.9, 0.9, now=fake_time[0])
        assert mode == TrackingMode.FUTON_MODE

    def test_futon_mode_with_no_cameras(self, sm_futon):
        """FUTON_MODE should work even with no camera data."""
        sm_futon.on_imu_pitch(70.0)
        mode = sm_futon.update(0.0, 0.0)
        assert mode == TrackingMode.FUTON_MODE

    def test_exit_dwell_time_prevents_flicker(self, monkeypatch):
        """Brief dip below exit threshold should NOT immediately exit FUTON_MODE."""
        config = ModeConfig(
            hysteresis_sec=0.0,
            futon_pitch_threshold=60.0,
            futon_exit_threshold=30.0,
            futon_dwell_time_sec=0.5,
        )
        sm = TrackingStateMachine(config=config)

        fake_time = [100.0]
        monkeypatch.setattr(time, "monotonic", lambda: fake_time[0])
        sm._last_osc_time = fake_time[0]

        # Enter FUTON_MODE (past dwell time)
        sm.on_imu_pitch(70.0)
        fake_time[0] = 100.6
        sm.on_imu_pitch(70.0)
        mode = sm.update(0.9, 0.9, now=fake_time[0])
        assert mode == TrackingMode.FUTON_MODE

        # Brief dip below exit threshold — should NOT exit yet
        fake_time[0] = 100.7
        sm.on_imu_pitch(20.0)
        mode = sm.update(0.9, 0.9, now=fake_time[0])
        assert mode == TrackingMode.FUTON_MODE  # Still in FUTON (dwell not elapsed)

        # After dwell time — NOW should exit
        fake_time[0] = 101.3
        sm.on_imu_pitch(20.0)
        mode = sm.update(0.9, 0.9, now=fake_time[0])
        assert mode != TrackingMode.FUTON_MODE

    def test_exit_dwell_cancelled_by_returning_to_lying(self, monkeypatch):
        """If user briefly sits up then lies back down, exit should be cancelled."""
        config = ModeConfig(
            hysteresis_sec=0.0,
            futon_pitch_threshold=60.0,
            futon_exit_threshold=30.0,
            futon_dwell_time_sec=0.5,
        )
        sm = TrackingStateMachine(config=config)

        fake_time = [100.0]
        monkeypatch.setattr(time, "monotonic", lambda: fake_time[0])
        sm._last_osc_time = fake_time[0]

        # Enter FUTON_MODE
        sm.on_imu_pitch(70.0)
        fake_time[0] = 100.6
        sm.on_imu_pitch(70.0)
        sm.update(0.9, 0.9, now=fake_time[0])
        assert sm.mode == TrackingMode.FUTON_MODE

        # Start exiting (pitch drops below exit threshold)
        fake_time[0] = 100.7
        sm.on_imu_pitch(20.0)

        # Before dwell completes, return to lying down
        fake_time[0] = 100.9
        sm.on_imu_pitch(70.0)
        mode = sm.update(0.9, 0.9, now=fake_time[0])
        assert mode == TrackingMode.FUTON_MODE  # Exit cancelled


class TestBothCamerasLostWithHysteresis:
    """Explicit tests for simultaneous dual camera loss with hysteresis (Phase 4)."""

    @pytest.fixture
    def sm_hyst(self):
        config = ModeConfig(hysteresis_sec=0.5)
        machine = TrackingStateMachine(config=config)
        machine._last_osc_time = time.monotonic()
        return machine

    def test_simultaneous_drop_bypasses_hysteresis(self, sm_hyst):
        """Both cameras < 0.05 should go straight to FULL_OCCLUSION."""
        sm_hyst.update(0.9, 0.9, now=time.monotonic())
        assert sm_hyst.mode == TrackingMode.VISIBLE

        mode = sm_hyst.update(0.01, 0.02, now=time.monotonic())
        assert mode == TrackingMode.FULL_OCCLUSION  # Immediate, no hysteresis

    def test_one_camera_lost_does_not_bypass(self, sm_hyst):
        """Only one camera below 0.05 should use normal hysteresis."""
        sm_hyst.update(0.9, 0.9, now=time.monotonic())
        now = time.monotonic()
        mode = sm_hyst.update(0.01, 0.9, now=now)
        # Should NOT be FULL_OCCLUSION yet (hysteresis active)
        assert mode != TrackingMode.FULL_OCCLUSION

    def test_recovery_from_both_lost(self, sm_hyst):
        """Recovery from FULL_OCCLUSION when cameras return."""
        sm_hyst.update(0.01, 0.01, now=time.monotonic())
        assert sm_hyst.mode == TrackingMode.FULL_OCCLUSION

        now = time.monotonic()
        sm_hyst.update(0.9, 0.9, now=now)
        # With hysteresis, might still be transitioning
        sm_hyst.update(0.9, 0.9, now=now + 0.6)
        assert sm_hyst.mode == TrackingMode.VISIBLE

    def test_both_cameras_return_at_different_times(self, sm_hyst):
        """One camera returns first, then the second."""
        now = time.monotonic()
        sm_hyst._last_osc_time = now
        sm_hyst.update(0.01, 0.01, now=now)
        assert sm_hyst.mode == TrackingMode.FULL_OCCLUSION

        # Cam1 returns but cam2 still down — should not be VISIBLE
        sm_hyst._last_osc_time = now + 0.1
        mode = sm_hyst.update(0.9, 0.01, now=now + 0.1)
        assert mode != TrackingMode.VISIBLE

        # Both cameras back — wait for hysteresis
        sm_hyst._last_osc_time = now + 0.7
        sm_hyst.update(0.9, 0.9, now=now + 0.7)
        sm_hyst._last_osc_time = now + 1.3
        sm_hyst.update(0.9, 0.9, now=now + 1.3)
        assert sm_hyst.mode == TrackingMode.VISIBLE
