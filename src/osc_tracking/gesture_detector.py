"""Gesture detection engine for recalibration and commands.

Detects hand position patterns from MediaPipe landmarks to trigger
actions like coordinate reset, mode switching, etc.
"""

import logging
import time
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class GestureConfig:
    hands_on_head_distance: float = 0.15  # meters
    hands_on_head_hold_sec: float = 2.0
    t_pose_arm_angle_threshold: float = 30.0  # degrees from horizontal
    t_pose_hold_sec: float = 3.0


class GestureDetector:
    """Detects predefined gestures from joint positions."""

    def __init__(self, config: GestureConfig | None = None):
        self.config = config or GestureConfig()
        self._hands_on_head_since: float | None = None
        self._t_pose_since: float | None = None
        self._callbacks: dict[str, list] = {
            "recalibrate": [],
            "t_pose": [],
        }

    def on(self, gesture: str, callback) -> None:
        if gesture in self._callbacks:
            self._callbacks[gesture].append(callback)

    def update(self, joints: dict[str, np.ndarray]) -> str | None:
        """Check for gestures given current joint positions.

        Args:
            joints: Dict mapping joint name to 3D position array.

        Returns:
            Gesture name if detected, None otherwise.
        """
        now = time.monotonic()

        # Hands on head → recalibrate
        head = joints.get("Head")
        left_elbow = joints.get("LeftElbow")
        right_elbow = joints.get("RightElbow")

        if head is not None and left_elbow is not None and right_elbow is not None:
            left_dist = np.linalg.norm(left_elbow - head)
            right_dist = np.linalg.norm(right_elbow - head)

            if (left_dist < self.config.hands_on_head_distance
                    and right_dist < self.config.hands_on_head_distance):
                if self._hands_on_head_since is None:
                    self._hands_on_head_since = now
                elif now - self._hands_on_head_since >= self.config.hands_on_head_hold_sec:
                    self._hands_on_head_since = None
                    self._fire("recalibrate")
                    return "recalibrate"
            else:
                self._hands_on_head_since = None

        # T-pose detection
        chest = joints.get("Chest")
        if chest is not None and left_elbow is not None and right_elbow is not None:
            left_vec = left_elbow - chest
            right_vec = right_elbow - chest

            # Check if arms are roughly horizontal
            left_angle = abs(np.degrees(np.arctan2(left_vec[1], np.linalg.norm(left_vec[[0, 2]]))))
            right_angle = abs(np.degrees(np.arctan2(right_vec[1], np.linalg.norm(right_vec[[0, 2]]))))

            if (left_angle < self.config.t_pose_arm_angle_threshold
                    and right_angle < self.config.t_pose_arm_angle_threshold):
                if self._t_pose_since is None:
                    self._t_pose_since = now
                elif now - self._t_pose_since >= self.config.t_pose_hold_sec:
                    self._t_pose_since = None
                    self._fire("t_pose")
                    return "t_pose"
            else:
                self._t_pose_since = None

        return None

    def _fire(self, gesture: str) -> None:
        for cb in self._callbacks.get(gesture, []):
            try:
                cb()
            except Exception:
                logger.exception("Gesture callback failed for %s", gesture)
