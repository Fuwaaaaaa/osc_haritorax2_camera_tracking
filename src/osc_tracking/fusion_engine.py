"""Fusion engine — orchestrates all tracking components.

Ties together the state machine, complementary filter, visual compass,
camera tracker, and OSC receiver/sender into a single update loop.

Architecture:
    ┌──────────────┐    ┌──────────────┐
    │ CameraTracker │    │ OSCReceiver   │
    │ (subprocess)  │    │ (thread)      │
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

from .camera_tracker import CameraTracker
from .complementary_filter import JOINT_NAMES, ComplementaryFilter
from .osc_receiver import OSCReceiver
from .osc_sender import OSCSender, TrackerOutput
from .state_machine import TrackingMode, TrackingStateMachine
from .visual_compass import compute_shoulder_yaw, correct_heading

logger = logging.getLogger(__name__)


class FusionEngine:
    """Main fusion loop that combines all tracking data sources."""

    def __init__(
        self,
        camera: CameraTracker,
        receiver: OSCReceiver,
        sender: OSCSender,
    ):
        self.camera = camera
        self.receiver = receiver
        self.sender = sender
        self.state_machine = TrackingStateMachine()
        self.filter = ComplementaryFilter()
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

        # Read camera data
        camera_joints = self.camera.read_joints()
        cam1_conf = 0.0
        cam2_conf = 0.0
        if camera_joints:
            confidences = [conf for _, conf in camera_joints.values()]
            if confidences:
                avg = sum(confidences) / len(confidences)
                cam1_conf = avg  # Simplified — real impl splits per camera
                cam2_conf = avg

        # Update OSC connectivity
        if self.receiver.is_connected:
            self.state_machine.on_osc_received()

        # Update state machine
        mode = self.state_machine.update(cam1_conf, cam2_conf, now)

        # Fuse each joint
        outputs: list[TrackerOutput] = []
        for joint_name in JOINT_NAMES:
            camera_pos = None
            confidence = 0.0
            if camera_joints and joint_name in camera_joints:
                camera_pos, confidence = camera_joints[joint_name]

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
                        imu_rotation = correct_heading(imu_rotation, camera_yaw)

            try:
                state = self.filter.update(
                    joint_name=joint_name,
                    camera_position=camera_pos,
                    imu_rotation=imu_rotation,
                    confidence=confidence,
                    dt=dt,
                )
            except Exception:
                logger.exception("Filter update failed for %s — resetting", joint_name)
                self.filter.reset_joint(joint_name)
                state = self.filter.joints[joint_name]

            outputs.append(TrackerOutput(
                position=state.position,
                rotation=state.rotation,
                joint_name=joint_name,
            ))

        # Send to VRChat
        self.sender.send(outputs)

        return mode

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
