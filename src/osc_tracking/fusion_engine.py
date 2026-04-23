"""Fusion engine — orchestrates all tracking components.

Ties together the state machine, complementary filter, visual compass,
camera tracker, and IMU receiver/sender into a single update loop.

Architecture:
    ┌──────────────┐    ┌──────────────┐
    │ CameraTracker │    │ IMUReceiver   │
    │ (subprocess)  │    │ (OSC or BLE)  │
    └──────┬───────┘    └──────┬───────┘
           │ joint data         │ bone rotation
           ▼                    ▼
    ┌──────────────────────────────────┐
    │          FusionEngine             │
    │  ┌────────────┐ ┌─────────────┐  │
    │  │StateMachine│ │Complementary│  │
    │  │            │ │   Filter    │  │
    │  └─────┬──────┘ └──────┬──────┘  │
    │        │ mode           │ fused   │
    │        ▼                ▼         │
    │  ┌────────────────────────────┐  │
    │  │     Visual Compass         │  │
    │  └────────────┬───────────────┘  │
    └───────────────┼──────────────────┘
                    │
                    ▼
             ┌──────────────┐
             │  OSCSender    │
             └──────────────┘
"""

import logging
import time

import numpy as np

from .application import EventBus
from .camera_protocol import VisionProvider
from .complementary_filter import JOINT_NAMES, ComplementaryFilter
from .config import TrackingConfig
from .domain import BoneId, Confidence, Position3D, Skeleton, SkeletonSnapshot
from .domain.events import (
    FrameProcessed,
    IMUDisconnected,
    IMUReconnected,
    OcclusionDetected,
    TrackingModeChanged,
)
from .osc_sender import OSCSender, TrackerOutput
from .pose_predictor import VelocityPredictor
from .receiver_protocol import IMUReceiver
from .state_machine import ModeConfig, TrackingMode, TrackingStateMachine
from .visual_compass import compute_shoulder_yaw, correct_heading

logger = logging.getLogger(__name__)

# Confidence assigned to predictor-substituted positions during occlusion.
# Deliberately below the default partial_threshold (0.3) so the fusion
# filter keeps the IMU as the primary truth source.
PREDICTED_CONFIDENCE = 0.2


class FusionEngine:
    """Main fusion loop that combines all tracking data sources."""

    def __init__(
        self,
        camera: VisionProvider,
        receiver: IMUReceiver,
        sender: OSCSender,
        config: TrackingConfig | None = None,
        event_bus: EventBus | None = None,
    ):
        self.camera = camera
        self.receiver = receiver
        self.sender = sender
        self.config = config or TrackingConfig()
        if self.config.futon_trigger_joint not in JOINT_NAMES:
            logger.warning(
                "futon_trigger_joint '%s' not in JOINT_NAMES, falling back to 'Chest'",
                self.config.futon_trigger_joint,
            )
            self.config.futon_trigger_joint = "Chest"
        self.state_machine = TrackingStateMachine(config=ModeConfig(
            visible_threshold=self.config.visible_threshold,
            partial_threshold=self.config.partial_threshold,
            osc_timeout_sec=self.config.osc_timeout_sec,
            hysteresis_sec=self.config.hysteresis_sec,
            futon_pitch_threshold=self.config.futon_pitch_threshold,
            futon_exit_threshold=self.config.futon_exit_threshold,
            futon_dwell_time_sec=self.config.futon_dwell_time_sec,
            futon_trigger_joint=self.config.futon_trigger_joint,
        ))
        self.filter = ComplementaryFilter(
            compass_blend_factor=self.config.compass_blend_factor,
            visible_threshold=self.config.visible_threshold,
            partial_threshold=self.config.partial_threshold,
        )
        self.predictor = VelocityPredictor(
            max_history=self.config.pose_predictor_max_history,
            stale_window_seconds=self.config.pose_predictor_stale_window_sec,
            max_predict_seconds=self.config.pose_predictor_max_predict_sec,
        )
        # Aggregate root — mirrors the fused state each cycle so UI /
        # output subsystems can observe a consistent frame snapshot
        # regardless of when they poll.
        self.skeleton = Skeleton()
        # Events: every fusion cycle publishes FrameProcessed; mode
        # transitions publish TrackingModeChanged; IMU link state flips
        # publish IMUDisconnected / IMUReconnected. Subsystems subscribe
        # instead of being called directly from main.py.
        self.events = event_bus or EventBus()
        self._prev_mode: TrackingMode | None = None
        self._prev_imu_connected: bool | None = None
        # Per-joint occlusion latch: True while the joint is currently
        # below partial_threshold. Used to fire OcclusionDetected only
        # on the visible→occluded edge, not every frame the joint stays
        # occluded.
        self._joint_occluded: dict[str, bool] = {}
        self._fps_ema: float = 0.0  # EMA-smoothed FPS for event consumers
        self._last_update: float = time.monotonic()
        self._running = False

    def update(self) -> TrackingMode:
        """Run one fusion cycle. Call this at ~30fps.

        Returns:
            The current tracking mode after this update.
        """
        now = time.monotonic()
        dt = now - self._last_update
        self._last_update = now

        # Clamp dt to prevent explosion after pause/sleep
        dt = min(dt, 0.1)

        # Update FPS estimate for event consumers (EMA with alpha=0.1)
        if dt > 0:
            inst_fps = 1.0 / dt
            self._fps_ema = (
                inst_fps if self._fps_ema == 0.0
                else 0.9 * self._fps_ema + 0.1 * inst_fps
            )

        # Read camera data (per-camera confidence from SharedMemory)
        camera_joints = self.camera.read_joints()
        cam1_conf = 0.0
        cam2_conf = 0.0
        if camera_joints:
            cam1_vals = [c1 for _, _, c1, _ in camera_joints.values()]
            cam2_vals = [c2 for _, _, _, c2 in camera_joints.values()]
            if cam1_vals:
                cam1_conf = sum(cam1_vals) / len(cam1_vals)
            if cam2_vals:
                cam2_conf = sum(cam2_vals) / len(cam2_vals)

        # Update IMU connectivity (receiver-agnostic: OSC, BLE, etc.)
        if self.receiver.is_connected:
            self.state_machine.on_imu_received()

        # Extract pitch from chest IMU for FUTON_MODE detection
        chest_rot = self.receiver.get_bone_rotation(self.config.futon_trigger_joint)
        if chest_rot is not None:
            euler = chest_rot.as_euler("YXZ")  # yaw, pitch, roll
            pitch_deg = np.degrees(euler[1])
            self.state_machine.on_imu_pitch(pitch_deg)

        # Update state machine
        mode = self.state_machine.update(cam1_conf, cam2_conf, now)

        # Feed the predictor every visible joint so it can extrapolate
        # positions that disappear in the next occlusion window.
        if self.config.pose_predictor_enabled and camera_joints:
            for jname, (pos, conf, _, _) in camera_joints.items():
                if conf >= self.config.partial_threshold:
                    self.predictor.observe(jname, pos, now)

        # Fuse each joint
        outputs: list[TrackerOutput] = []
        is_futon = mode == TrackingMode.FUTON_MODE
        occluded = mode in (TrackingMode.FULL_OCCLUSION, TrackingMode.PARTIAL_OCCLUSION)
        for joint_name in JOINT_NAMES:
            camera_pos = None
            confidence = 0.0
            if not is_futon and camera_joints and joint_name in camera_joints:
                camera_pos, confidence, _, _ = camera_joints[joint_name]

            # Per-joint occlusion edge detection: fire OcclusionDetected
            # only when a joint was visible in a prior frame and drops
            # below partial_threshold this frame. Joints never observed
            # visible don't count as "becoming occluded" — they simply
            # never arrived.
            is_raw_occluded = confidence < self.config.partial_threshold
            prev = self._joint_occluded.get(joint_name)  # True/False/None
            if prev is False and is_raw_occluded:
                try:
                    self.events.publish(OcclusionDetected(
                        timestamp=now,
                        bone=BoneId(joint_name),
                    ))
                except ValueError:
                    pass  # non-canonical bone name; skip
            # Only record state after a joint has been observed visible
            # at least once, so first-frame "occluded" from an unseen
            # joint doesn't latch as a transition target.
            if not is_raw_occluded or prev is not None:
                self._joint_occluded[joint_name] = is_raw_occluded

            # Predictor fallback: during occlusion, substitute a predicted
            # position (at reduced confidence) when the camera has nothing
            # to say. Skip in FUTON mode where the filter already trusts
            # IMU exclusively.
            if (
                self.config.pose_predictor_enabled
                and not is_futon
                and occluded
                and camera_pos is None
            ):
                predicted = self.predictor.predict(joint_name, now)
                if predicted is not None:
                    camera_pos = predicted
                    # Stay just below partial_threshold so the filter weighs
                    # IMU more than the predicted camera position.
                    confidence = PREDICTED_CONFIDENCE

            imu_rotation = self.receiver.get_bone_rotation(joint_name)

            # Apply visual compass for chest tracker using shoulder positions
            if (
                joint_name == "Chest"
                and imu_rotation is not None
                and camera_joints
                and mode in (TrackingMode.VISIBLE, TrackingMode.SINGLE_CAM_DEGRADED)
            ):
                # Camera tracker provides shoulder data via "Chest" joint
                # (averaged from MediaPipe landmarks #11 + #12).
                # For Visual Compass we need individual shoulders, which
                # requires raw landmark access. For now use LeftElbow/RightElbow
                # as a rough proxy for shoulder direction.
                left_proxy = camera_joints.get("LeftElbow")
                right_proxy = camera_joints.get("RightElbow")
                if left_proxy is not None and right_proxy is not None:
                    camera_yaw = compute_shoulder_yaw(left_proxy[0], right_proxy[0])
                    if camera_yaw is not None:
                        imu_rotation = correct_heading(
                            imu_rotation,
                            camera_yaw,
                            blend_factor=self.config.compass_blend_factor,
                        )

            try:
                state = self.filter.update(
                    joint_name=joint_name,
                    camera_position=camera_pos,
                    imu_rotation=imu_rotation,
                    confidence=confidence,
                    dt=dt,
                )
            except (ValueError, RuntimeError, np.linalg.LinAlgError):
                logger.exception("Filter update failed for %s — resetting", joint_name)
                self.filter.reset_joint(joint_name)
                state = self.filter.joints[joint_name]

            outputs.append(TrackerOutput(
                position=state.position,
                rotation=state.rotation,
                joint_name=joint_name,
            ))

            # Mirror the fused joint into the aggregate for downstream
            # observers. Domain types enforce invariants (finite position,
            # [0,1] confidence) so a malformed state surfaces here, not
            # deep inside a subsystem.
            try:
                self.skeleton.update_joint(
                    BoneId(joint_name),
                    Position3D.from_array(state.position),
                    state.rotation,
                    Confidence(min(max(float(confidence), 0.0), 1.0)),
                )
            except ValueError:
                # Filter produced a non-finite position — drop from the
                # aggregate this frame (the legacy TrackerOutput path
                # still carries the raw numbers).
                pass

        self.skeleton.set_mode(mode)
        self.skeleton.set_timestamp(now)

        # Send to VRChat
        self.sender.send(outputs)

        # Publish domain events. Subsystems subscribe in main.py.
        self._publish_frame_events(mode, now)

        return mode

    def _publish_frame_events(self, mode: TrackingMode, now: float) -> None:
        """Emit per-frame and transition events."""
        if self._prev_mode is not None and self._prev_mode != mode:
            self.events.publish(TrackingModeChanged(
                timestamp=now,
                previous=self._prev_mode,
                current=mode,
            ))
        self._prev_mode = mode

        imu_connected = self.receiver.is_connected
        if self._prev_imu_connected is True and imu_connected is False:
            self.events.publish(IMUDisconnected(timestamp=now))
        elif self._prev_imu_connected is False and imu_connected is True:
            self.events.publish(IMUReconnected(timestamp=now))
        self._prev_imu_connected = imu_connected

        self.events.publish(FrameProcessed(
            timestamp=now,
            snapshot=self.skeleton.snapshot(),
            fps=self._fps_ema,
        ))

    def snapshot(self) -> SkeletonSnapshot:
        """Return an immutable frame snapshot for observers."""
        return self.skeleton.snapshot()

    def start(self) -> None:
        """Start all subsystems."""
        self.camera.start()
        self.receiver.start()
        self.sender.connect()
        self._running = True
        logger.info("Fusion engine started")

    def stop(self) -> None:
        """Stop all subsystems."""
        self._running = False
        self.camera.stop()
        self.receiver.stop()
        self.sender.close()
        logger.info("Fusion engine stopped")
