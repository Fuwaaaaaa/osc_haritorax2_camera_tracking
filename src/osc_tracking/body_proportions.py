"""Body proportion configuration — scale skeleton to user's body.

Adjusts joint offsets based on height, arm length, leg length, etc.
"""

from dataclasses import dataclass

import numpy as np


@dataclass
class BodyProportions:
    """User's body measurements in meters."""
    height: float = 1.70
    arm_span: float = 1.70  # Fingertip to fingertip
    shoulder_width: float = 0.40
    hip_width: float = 0.30
    torso_length: float = 0.45  # Hip to shoulder
    upper_leg: float = 0.45
    lower_leg: float = 0.42
    upper_arm: float = 0.30
    lower_arm: float = 0.25

    @classmethod
    def from_height(cls, height: float) -> "BodyProportions":
        """Estimate proportions from height using anthropometric ratios."""
        return cls(
            height=height,
            arm_span=height * 1.0,
            shoulder_width=height * 0.235,
            hip_width=height * 0.176,
            torso_length=height * 0.265,
            upper_leg=height * 0.265,
            lower_leg=height * 0.247,
            upper_arm=height * 0.176,
            lower_arm=height * 0.147,
        )

    def get_joint_offsets(self) -> dict[str, np.ndarray]:
        """Get T-pose joint positions relative to Hips."""
        hip_y = self.upper_leg + self.lower_leg
        return {
            "Hips": np.array([0.0, hip_y, 0.0]),
            "Chest": np.array([0.0, hip_y + self.torso_length * 0.6, 0.0]),
            "Head": np.array([0.0, hip_y + self.torso_length + 0.15, 0.0]),
            "LeftElbow": np.array([-self.shoulder_width / 2 - self.upper_arm, hip_y + self.torso_length, 0.0]),
            "RightElbow": np.array([self.shoulder_width / 2 + self.upper_arm, hip_y + self.torso_length, 0.0]),
            "LeftKnee": np.array([-self.hip_width / 2, self.lower_leg, 0.0]),
            "RightKnee": np.array([self.hip_width / 2, self.lower_leg, 0.0]),
            "LeftFoot": np.array([-self.hip_width / 2, 0.0, 0.0]),
            "RightFoot": np.array([self.hip_width / 2, 0.0, 0.0]),
        }

    def scale_factor(self) -> float:
        """Scale factor relative to default 1.70m skeleton."""
        return self.height / 1.70
