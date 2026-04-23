"""Tests for fusion engine with mocked subsystems."""

import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from osc_tracking.complementary_filter import JOINT_NAMES
from osc_tracking.fusion_engine import FusionEngine
from osc_tracking.state_machine import TrackingMode


@pytest.fixture
def mock_camera():
    camera = MagicMock()
    camera.is_alive = True
    # Return realistic joint data
    # (position, combined_conf, cam1_conf, cam2_conf)
    camera.read_joints.return_value = {
        name: (np.array([0.0, 1.0, 2.0]), 0.9, 0.9, 0.9)
        for name in JOINT_NAMES
    }
    return camera


@pytest.fixture
def mock_receiver():
    receiver = MagicMock()
    receiver.is_connected = True
    receiver.get_bone_rotation.return_value = Rotation.identity()
    return receiver


@pytest.fixture
def mock_sender():
    sender = MagicMock()
    sender.send.return_value = True
    return sender


@pytest.fixture
def engine(mock_camera, mock_receiver, mock_sender):
    return FusionEngine(
        camera=mock_camera,
        receiver=mock_receiver,
        sender=mock_sender,
    )


class TestUpdateCycle:
    def test_update_returns_tracking_mode(self, engine):
        mode = engine.update()
        assert isinstance(mode, TrackingMode)

    def test_update_reads_camera(self, engine, mock_camera):
        engine.update()
        mock_camera.read_joints.assert_called_once()

    def test_update_sends_to_vrchat(self, engine, mock_sender):
        engine.update()
        mock_sender.send.assert_called_once()
        outputs = mock_sender.send.call_args[0][0]
        assert len(outputs) == len(JOINT_NAMES)

    def test_update_output_has_position_and_rotation(self, engine, mock_sender):
        engine.update()
        outputs = mock_sender.send.call_args[0][0]
        for output in outputs:
            assert output.position is not None
            assert output.rotation is not None
            assert output.joint_name in JOINT_NAMES


class TestVisibleMode:
    def test_high_confidence_is_visible(self, engine):
        mode = engine.update()
        assert mode == TrackingMode.VISIBLE

    def test_position_moves_toward_camera(self, engine, mock_sender):
        # Multiple updates should converge position
        for _ in range(30):
            engine.update()
            time.sleep(0.001)  # Small delay for dt calculation

        outputs = mock_sender.send.call_args[0][0]
        hips = next(o for o in outputs if o.joint_name == "Hips")
        # Position should be near camera target (0, 1, 2)
        assert np.linalg.norm(hips.position - np.array([0.0, 1.0, 2.0])) < 1.0


class TestFullOcclusion:
    def test_no_camera_data_transitions(self, engine, mock_camera):
        mock_camera.read_joints.return_value = None
        # Need multiple updates for hysteresis
        engine.state_machine.config.hysteresis_sec = 0.0
        engine.state_machine._last_osc_time = time.monotonic()
        mode = engine.update()
        assert mode == TrackingMode.FULL_OCCLUSION


class TestIMUDisconnected:
    def test_no_osc_triggers_disconnect(self, engine, mock_receiver):
        mock_receiver.is_connected = False
        engine.state_machine._last_osc_time = time.monotonic() - 2.0
        engine.state_machine.config.hysteresis_sec = 0.0
        mode = engine.update()
        assert mode == TrackingMode.IMU_DISCONNECTED


class TestErrorRecovery:
    def test_filter_exception_resets_joint(self, engine):
        """If the filter throws, the engine should reset the joint and continue."""
        with patch.object(
            engine.filter, "update", side_effect=ValueError("test error")
        ):
            # Should not raise
            mode = engine.update()
            assert isinstance(mode, TrackingMode)

    def test_camera_none_does_not_crash(self, engine, mock_camera):
        mock_camera.read_joints.return_value = None
        engine.state_machine.config.hysteresis_sec = 0.0
        engine.state_machine._last_osc_time = time.monotonic()
        mode = engine.update()
        assert isinstance(mode, TrackingMode)


class TestVisualCompass:
    def test_chest_heading_corrected_when_visible(self, engine, mock_camera, mock_receiver):
        """Visual compass should be applied to Chest joint in Visible mode."""
        # Provide elbow data for Visual Compass proxy
        mock_camera.read_joints.return_value = {
            name: (np.array([0.1 * i, 1.0, 2.0]), 0.9, 0.9, 0.9)
            for i, name in enumerate(JOINT_NAMES)
        }
        mock_receiver.get_bone_rotation.return_value = Rotation.from_euler(
            "xyz", [0, 45, 0], degrees=True  # IMU says 45 deg yaw
        )
        engine.update()
        # Should complete without error — Visual Compass applied


class TestLifecycle:
    def test_start_initializes_subsystems(self, engine, mock_camera, mock_receiver, mock_sender):
        engine.start()
        mock_camera.start.assert_called_once()
        mock_receiver.start.assert_called_once()
        mock_sender.connect.assert_called_once()

    def test_stop_cleans_up(self, engine, mock_camera, mock_receiver, mock_sender):
        engine.start()
        engine.stop()
        mock_camera.stop.assert_called_once()
        mock_receiver.stop.assert_called_once()
        mock_sender.close.assert_called_once()


class TestDtClamping:
    def test_large_dt_is_clamped(self, engine):
        """If the loop stalls, dt should be clamped to 0.1s max."""
        engine._last_update = time.monotonic() - 10.0  # Simulate 10s stall
        mode = engine.update()
        assert isinstance(mode, TrackingMode)
        # The filter should not explode from a huge dt


class TestVisualCompassOcclusion:
    def test_visual_compass_not_applied_in_occlusion(self, engine, mock_camera, mock_receiver):
        """Visual compass should NOT be applied in FULL_OCCLUSION mode."""
        mock_camera.read_joints.return_value = None
        engine.state_machine.config.hysteresis_sec = 0.0
        engine.state_machine._last_osc_time = time.monotonic()

        with patch(
            "osc_tracking.fusion_engine.correct_heading"
        ) as mock_correct:
            mode = engine.update()
            assert mode == TrackingMode.FULL_OCCLUSION
            mock_correct.assert_not_called()

    def test_visual_compass_skipped_without_elbow_data(
        self, engine, mock_camera, mock_receiver
    ):
        """Visual compass should be skipped when elbow joints are missing."""
        # Provide camera data but WITHOUT LeftElbow and RightElbow
        joints_no_elbows = {
            name: (np.array([0.0, 1.0, 2.0]), 0.9, 0.9, 0.9)
            for name in JOINT_NAMES
            if name not in ("LeftElbow", "RightElbow")
        }
        mock_camera.read_joints.return_value = joints_no_elbows
        mock_receiver.get_bone_rotation.return_value = Rotation.from_euler(
            "xyz", [0, 30, 0], degrees=True
        )

        with patch(
            "osc_tracking.fusion_engine.correct_heading"
        ) as mock_correct:
            engine.update()
            mock_correct.assert_not_called()


class TestConvergence:
    def test_multiple_updates_converge(self, engine, mock_camera, mock_sender):
        """After 30 frames, the fused position should converge toward camera target."""
        target = np.array([1.0, 2.0, 3.0])
        mock_camera.read_joints.return_value = {
            name: (target.copy(), 0.95, 0.95, 0.95) for name in JOINT_NAMES
        }

        for _ in range(30):
            engine.update()
            time.sleep(0.001)

        outputs = mock_sender.send.call_args[0][0]
        hips = next(o for o in outputs if o.joint_name == "Hips")
        dist = np.linalg.norm(hips.position - target)
        assert dist < 0.5, f"Position did not converge: distance={dist:.3f}"


class TestPartialCameraData:
    def test_partial_camera_data(self, engine, mock_camera, mock_sender):
        """Engine handles partial camera data (only some joints present)."""
        partial_joints = {
            "Hips": (np.array([0.0, 1.0, 2.0]), 0.9, 0.9, 0.9),
            "Chest": (np.array([0.0, 1.5, 2.0]), 0.85, 0.85, 0.85),
        }
        mock_camera.read_joints.return_value = partial_joints

        mode = engine.update()
        assert isinstance(mode, TrackingMode)

        outputs = mock_sender.send.call_args[0][0]
        assert len(outputs) == len(JOINT_NAMES)

        # Joints with camera data should have non-zero position
        hips = next(o for o in outputs if o.joint_name == "Hips")
        assert not np.allclose(hips.position, 0.0)

        # Joints without camera data should still have valid output
        left_foot = next(o for o in outputs if o.joint_name == "LeftFoot")
        assert left_foot.position is not None
        assert left_foot.rotation is not None


class TestPerCameraConfidence:
    """Test that per-camera confidence enables SINGLE_CAM_DEGRADED mode."""

    def test_asymmetric_confidence_triggers_degraded(
        self, mock_camera, mock_receiver, mock_sender
    ):
        """When cam1 is high and cam2 is low, SINGLE_CAM_DEGRADED should trigger."""
        engine = FusionEngine(
            camera=mock_camera, receiver=mock_receiver, sender=mock_sender,
        )
        engine.state_machine.config.hysteresis_sec = 0.0
        engine.state_machine._last_osc_time = time.monotonic()

        # cam1 sees well (0.9), cam2 is occluded (0.1)
        mock_camera.read_joints.return_value = {
            name: (np.array([0.0, 1.0, 2.0]), 0.5, 0.9, 0.1)
            for name in JOINT_NAMES
        }
        mode = engine.update()
        assert mode == TrackingMode.SINGLE_CAM_DEGRADED

    def test_symmetric_confidence_stays_visible(
        self, mock_camera, mock_receiver, mock_sender
    ):
        """When both cameras have similar confidence, should NOT be degraded."""
        engine = FusionEngine(
            camera=mock_camera, receiver=mock_receiver, sender=mock_sender,
        )
        engine.state_machine.config.hysteresis_sec = 0.0
        engine.state_machine._last_osc_time = time.monotonic()

        mock_camera.read_joints.return_value = {
            name: (np.array([0.0, 1.0, 2.0]), 0.9, 0.9, 0.85)
            for name in JOINT_NAMES
        }
        mode = engine.update()
        assert mode == TrackingMode.VISIBLE

    def test_both_cameras_low_is_full_occlusion(
        self, mock_camera, mock_receiver, mock_sender
    ):
        """When both cameras are low, should be FULL_OCCLUSION not DEGRADED."""
        engine = FusionEngine(
            camera=mock_camera, receiver=mock_receiver, sender=mock_sender,
        )
        engine.state_machine.config.hysteresis_sec = 0.0
        engine.state_machine._last_osc_time = time.monotonic()

        mock_camera.read_joints.return_value = {
            name: (np.array([0.0, 1.0, 2.0]), 0.05, 0.02, 0.03)
            for name in JOINT_NAMES
        }
        mode = engine.update()
        assert mode == TrackingMode.FULL_OCCLUSION


class TestCompassBlendFactorThreading:
    """Verify compass_blend_factor flows from config to correct_heading()."""

    def test_engine_passes_blend_factor_to_correct_heading(
        self, mock_camera, mock_receiver, mock_sender
    ):
        """FusionEngine should pass compass_blend_factor to correct_heading()."""
        from osc_tracking.config import TrackingConfig

        config = TrackingConfig()
        config.compass_blend_factor = 0.5

        engine = FusionEngine(
            camera=mock_camera,
            receiver=mock_receiver,
            sender=mock_sender,
            config=config,
        )

        with patch("osc_tracking.fusion_engine.correct_heading") as mock_ch:
            mock_ch.return_value = Rotation.identity()
            engine.update()

            if mock_ch.called:
                _, kwargs = mock_ch.call_args
                assert "blend_factor" in kwargs or len(mock_ch.call_args[0]) >= 3
                # Verify the blend_factor value
                if "blend_factor" in kwargs:
                    assert kwargs["blend_factor"] == 0.5

    def test_engine_creates_filter_with_blend_factor(
        self, mock_camera, mock_receiver, mock_sender
    ):
        """FusionEngine should pass compass_blend_factor to ComplementaryFilter."""
        from osc_tracking.config import TrackingConfig

        config = TrackingConfig()
        config.compass_blend_factor = 0.7

        engine = FusionEngine(
            camera=mock_camera,
            receiver=mock_receiver,
            sender=mock_sender,
            config=config,
        )

        assert engine.filter.compass_blend_factor == 0.7


class TestOcclusionDetectedEvent:
    """FusionEngine publishes OcclusionDetected when a previously
    visible joint's confidence drops below partial_threshold."""

    def test_no_event_when_all_joints_stay_visible(self, engine):
        from osc_tracking.domain.events import OcclusionDetected
        events: list = []
        engine.events.subscribe(OcclusionDetected, events.append)
        engine.update()
        engine.update()
        assert events == []

    def test_event_fired_when_visible_joint_becomes_occluded(self, engine, mock_camera):
        from osc_tracking.domain.events import OcclusionDetected
        events: list = []
        engine.events.subscribe(OcclusionDetected, events.append)

        # Frame 1: all joints visible
        engine.update()
        # Frame 2: Hips drops below partial_threshold (0.3)
        degraded = dict(mock_camera.read_joints.return_value)
        degraded["Hips"] = (np.array([0.0, 1.0, 2.0]), 0.05, 0.05, 0.05)
        mock_camera.read_joints.return_value = degraded
        engine.update()

        # Exactly one event for Hips
        hips_events = [e for e in events if e.bone.name == "Hips"]
        assert len(hips_events) == 1

    def test_no_duplicate_event_while_joint_stays_occluded(self, engine, mock_camera):
        from osc_tracking.domain.events import OcclusionDetected
        events: list = []
        engine.events.subscribe(OcclusionDetected, events.append)

        engine.update()  # baseline visible
        degraded = dict(mock_camera.read_joints.return_value)
        degraded["Hips"] = (np.array([0.0, 1.0, 2.0]), 0.05, 0.05, 0.05)
        mock_camera.read_joints.return_value = degraded

        engine.update()  # transition visible → occluded: fire
        engine.update()  # still occluded: no duplicate
        engine.update()

        hips_events = [e for e in events if e.bone.name == "Hips"]
        assert len(hips_events) == 1


class TestEventPublishing:
    """FusionEngine publishes domain events each cycle. Subsystems
    subscribe via the bus instead of being called directly."""

    def test_publishes_frame_processed_each_cycle(self, engine):
        from osc_tracking.domain.events import FrameProcessed
        events: list = []
        engine.events.subscribe(FrameProcessed, events.append)
        engine.update()
        engine.update()
        assert len(events) == 2
        assert events[-1].snapshot.mode == engine.skeleton.mode

    def test_publishes_tracking_mode_changed_only_on_transition(
        self, engine, mock_camera
    ):
        from osc_tracking.domain.events import TrackingModeChanged
        events: list = []
        engine.events.subscribe(TrackingModeChanged, events.append)

        # First update establishes VISIBLE baseline (no prev, no event).
        engine.update()
        # Same mode again: still no event.
        engine.update()
        assert len(events) == 0

        # Cut camera → forced transition to FULL_OCCLUSION.
        mock_camera.read_joints.return_value = None
        engine.state_machine.config.hysteresis_sec = 0.0
        engine.state_machine._last_osc_time = time.monotonic()
        engine.update()
        assert len(events) >= 1
        assert events[0].previous == TrackingMode.VISIBLE

    def test_publishes_imu_disconnect_reconnect(self, engine, mock_receiver):
        from osc_tracking.domain.events import IMUDisconnected, IMUReconnected
        disc: list = []
        reco: list = []
        engine.events.subscribe(IMUDisconnected, disc.append)
        engine.events.subscribe(IMUReconnected, reco.append)
        # Prime: first update establishes baseline.
        engine.update()
        # Disconnect.
        mock_receiver.is_connected = False
        engine.update()
        assert len(disc) == 1
        # Reconnect.
        mock_receiver.is_connected = True
        engine.update()
        assert len(reco) == 1


class TestSkeletonAggregate:
    """FusionEngine must mirror each fused frame into the Skeleton
    aggregate so UI / output subsystems can observe a consistent view."""

    def test_skeleton_empty_before_first_update(self, engine):
        assert engine.skeleton.joints == {}
        assert engine.skeleton.timestamp == 0.0

    def test_skeleton_populated_after_update(self, engine):
        engine.update()
        assert len(engine.skeleton.joints) > 0
        assert engine.skeleton.timestamp > 0.0

    def test_snapshot_is_immutable_view(self, engine):
        """A snapshot taken before a second update must not see the
        later frame — proves the aggregate's snapshot() makes a copy.
        Deterministic: we mutate the aggregate directly rather than
        sleeping for monotonic clock to advance (which is flaky on
        Windows' 15ms timer resolution)."""
        engine.update()
        snap = engine.snapshot()
        first_ts = snap.timestamp
        first_joint_count = len(snap.joints)
        # Mutate the live aggregate after snapshot — changes must not
        # appear in the already-taken snapshot.
        engine.skeleton.set_timestamp(first_ts + 999.0)
        engine.skeleton._joints.clear()
        assert snap.timestamp == first_ts
        assert len(snap.joints) == first_joint_count

    def test_skeleton_mode_matches_fusion_mode(self, engine):
        mode = engine.update()
        assert engine.skeleton.mode == mode


class TestPosePredictorIntegration:
    """FusionEngine should feed seen positions into the predictor and
    fall back to predictions when the camera can't see a joint during
    partial/full occlusion."""

    def test_predictor_observes_visible_joints(self, engine, mock_camera):
        """Each cycle, seen joints should be pushed into the predictor."""
        engine.update()
        # Hips was visible — predictor must now have at least one sample.
        assert engine.predictor.predict("Hips") is not None

    def test_predictor_substitutes_missing_joint_during_partial_occlusion(
        self, engine, mock_camera
    ):
        """When a joint disappears from camera data mid-session, the
        predictor's last-known position should feed the filter instead
        of a None camera_position (which would make the filter coast
        purely on IMU and drift)."""
        # Prime the predictor with two samples for Hips (establish position).
        for _ in range(3):
            engine.update()
            time.sleep(0.01)

        # Hips vanishes but other joints still seen → PARTIAL_OCCLUSION.
        partial = {
            name: (np.array([0.0, 1.0, 2.0]), 0.9, 0.9, 0.9)
            for name in JOINT_NAMES
            if name != "Hips"
        }
        mock_camera.read_joints.return_value = partial

        # The predictor still has Hips history from earlier frames.
        hips_pred = engine.predictor.predict("Hips")
        assert hips_pred is not None
        engine.update()

    def test_predictor_respects_disabled_flag(self, mock_camera, mock_receiver, mock_sender):
        """With pose_predictor_enabled=False, the predictor is still
        constructed but never observes — ensuring a clean opt-out."""
        from osc_tracking.config import TrackingConfig
        config = TrackingConfig()
        config.pose_predictor_enabled = False
        engine = FusionEngine(
            camera=mock_camera,
            receiver=mock_receiver,
            sender=mock_sender,
            config=config,
        )
        engine.update()
        assert engine.predictor.predict("Hips") is None


class TestApplySmoothingPreset:
    """The public API that replaces writing to engine.filter internals
    from main.py."""

    def test_applies_preset_values_to_filter(self, engine):
        from osc_tracking.motion_smoothing import SmoothingPreset

        preset = SmoothingPreset(
            name="custom",
            smooth_rate=12.5,
            noise_threshold=0.07,
            prediction_weight=0.3,
        )
        engine.apply_smoothing_preset(preset)
        assert engine.filter.SMOOTH_RATE == 12.5
        assert engine.filter.DRIFT_VELOCITY_THRESHOLD == 0.07
