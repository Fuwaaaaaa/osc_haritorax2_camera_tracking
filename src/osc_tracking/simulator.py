"""Simulation mode — run the full pipeline with synthetic data.

Generates realistic human motion data (walking, sitting, lying down)
without any hardware. Useful for debugging, demos, and parameter tuning.

Usage:
    python -m osc_tracking.tools.simulate
"""

import math
from dataclasses import dataclass

import numpy as np
from scipy.spatial.transform import Rotation

from .complementary_filter import JOINT_NAMES


@dataclass
class SimulationConfig:
    """Configuration for motion simulation."""
    motion_type: str = "idle"  # idle, walking, lying, dancing
    speed: float = 1.0
    noise_level: float = 0.01  # Gaussian noise added to positions
    occlusion_probability: float = 0.0  # Chance of simulated occlusion per frame
    imu_drift_rate: float = 0.001  # Radians per second of yaw drift


class MotionSimulator:
    """Generates synthetic tracking data for testing."""

    def __init__(self, config: SimulationConfig | None = None):
        self.config = config or SimulationConfig()
        self._time = 0.0
        self._imu_drift = 0.0

    def generate_frame(self, dt: float) -> dict[str, tuple[np.ndarray, Rotation, float]]:
        """Generate one frame of synthetic data.

        Returns:
            Dict mapping joint name to (position, rotation, confidence).
        """
        self._time += dt
        self._imu_drift += self.config.imu_drift_rate * dt
        t = self._time * self.config.speed

        generators = {
            "idle": self._idle_pose,
            "walking": self._walking_pose,
            "lying": self._lying_pose,
            "dancing": self._dancing_pose,
        }
        gen = generators.get(self.config.motion_type, self._idle_pose)
        frame = gen(t)

        # Add noise
        for name in frame:
            pos, rot, conf = frame[name]
            noise = np.random.normal(0, self.config.noise_level, 3)
            pos = pos + noise

            # Simulate IMU drift on rotation
            drift_rot = Rotation.from_euler("y", self._imu_drift)
            rot = drift_rot * rot

            # Simulate occlusion
            if np.random.random() < self.config.occlusion_probability:
                conf = 0.1

            frame[name] = (pos, rot, conf)

        return frame

    def _base_skeleton(self) -> dict[str, np.ndarray]:
        """T-pose skeleton positions (meters)."""
        return {
            "Hips": np.array([0.0, 1.0, 0.0]),
            "Chest": np.array([0.0, 1.3, 0.0]),
            "Head": np.array([0.0, 1.6, 0.0]),
            "LeftFoot": np.array([-0.1, 0.05, 0.0]),
            "RightFoot": np.array([0.1, 0.05, 0.0]),
            "LeftKnee": np.array([-0.1, 0.5, 0.0]),
            "RightKnee": np.array([0.1, 0.5, 0.0]),
            "LeftElbow": np.array([-0.4, 1.3, 0.0]),
            "RightElbow": np.array([0.4, 1.3, 0.0]),
        }

    def _idle_pose(self, t: float) -> dict[str, tuple[np.ndarray, Rotation, float]]:
        """Standing still with subtle breathing motion."""
        skeleton = self._base_skeleton()
        breath = math.sin(t * 0.5) * 0.005
        result = {}
        for name, pos in skeleton.items():
            pos = pos.copy()
            if name in ("Chest", "Head"):
                pos[1] += breath
            rot = Rotation.identity()
            result[name] = (pos, rot, 0.9)
        return result

    def _walking_pose(self, t: float) -> dict[str, tuple[np.ndarray, Rotation, float]]:
        """Walking animation with leg and arm swing."""
        skeleton = self._base_skeleton()
        stride = 0.3
        result = {}
        for name, pos in skeleton.items():
            pos = pos.copy()
            rot = Rotation.identity()

            if name == "Hips":
                pos[2] += math.sin(t * 2) * stride * 0.5
                pos[1] += abs(math.sin(t * 4)) * 0.02
            elif name == "LeftFoot":
                pos[2] += math.sin(t * 2) * stride
                pos[1] += max(0, math.sin(t * 2)) * 0.1
            elif name == "RightFoot":
                pos[2] += math.sin(t * 2 + math.pi) * stride
                pos[1] += max(0, math.sin(t * 2 + math.pi)) * 0.1
            elif name == "LeftElbow":
                swing = math.sin(t * 2 + math.pi) * 0.2
                rot = Rotation.from_euler("x", swing)
            elif name == "RightElbow":
                swing = math.sin(t * 2) * 0.2
                rot = Rotation.from_euler("x", swing)

            result[name] = (pos, rot, 0.85)
        return result

    def _lying_pose(self, t: float) -> dict[str, tuple[np.ndarray, Rotation, float]]:
        """Lying down (simulates blanket/futon scenario)."""
        result = {}
        base_y = 0.15  # Near floor
        for name in JOINT_NAMES:
            pos = np.array([0.0, base_y, 0.0])

            if name == "Head":
                pos = np.array([0.0, base_y + 0.05, -0.8])
            elif name == "Chest":
                pos = np.array([0.0, base_y + 0.03, -0.4])
            elif name == "Hips":
                pos = np.array([0.0, base_y, 0.0])
            elif name == "LeftFoot":
                pos = np.array([-0.15, base_y, 0.8])
            elif name == "RightFoot":
                pos = np.array([0.15, base_y, 0.8])
            elif name == "LeftKnee":
                pos = np.array([-0.1, base_y + 0.02, 0.4])
            elif name == "RightKnee":
                pos = np.array([0.1, base_y + 0.02, 0.4])

            # Subtle breathing
            breath = math.sin(t * 0.4) * 0.003
            pos[1] += breath

            rot = Rotation.from_euler("x", -math.pi / 2)  # Lying on back
            # Low confidence — simulates blanket occlusion
            conf = 0.2 + 0.1 * math.sin(t * 0.1)
            result[name] = (pos, rot, conf)
        return result

    def _dancing_pose(self, t: float) -> dict[str, tuple[np.ndarray, Rotation, float]]:
        """Energetic dancing motion."""
        skeleton = self._base_skeleton()
        result = {}
        for name, pos in skeleton.items():
            pos = pos.copy()

            if name == "Hips":
                pos[0] += math.sin(t * 3) * 0.15
                pos[1] += abs(math.sin(t * 6)) * 0.05
            elif name in ("LeftElbow", "RightElbow"):
                angle = t * 4 + (0 if "Left" in name else math.pi)
                pos[0] += math.sin(angle) * 0.2
                pos[1] += math.cos(angle) * 0.2 + 0.2

            rot = Rotation.from_euler("y", math.sin(t * 2) * 0.3)
            result[name] = (pos, rot, 0.9)
        return result
