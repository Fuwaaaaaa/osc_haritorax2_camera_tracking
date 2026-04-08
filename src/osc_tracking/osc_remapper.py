"""OSC address remapper — custom mapping for different VR applications.

Transforms OSC output addresses based on configurable profiles
for VRChat, Resonite, ChilloutVR, etc.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class OSCProfile:
    """Address mapping profile for a VR application."""
    name: str
    position_pattern: str  # e.g., "/tracking/trackers/{id}/position"
    rotation_pattern: str  # e.g., "/tracking/trackers/{id}/rotation"
    joint_ids: dict[str, int] = field(default_factory=dict)
    rotation_format: str = "euler"  # "euler" or "quaternion"


DEFAULT_PROFILES = {
    "vrchat": OSCProfile(
        name="VRChat",
        position_pattern="/tracking/trackers/{id}/position",
        rotation_pattern="/tracking/trackers/{id}/rotation",
        joint_ids={"Hips": 1, "Chest": 2, "Head": 3, "LeftFoot": 4, "RightFoot": 5,
                   "LeftKnee": 6, "RightKnee": 7, "LeftElbow": 8},
        rotation_format="euler",
    ),
    "vmc": OSCProfile(
        name="VMC Protocol",
        position_pattern="/VMC/Ext/Bone/Pos",
        rotation_pattern="/VMC/Ext/Bone/Pos",
        joint_ids={"Hips": 0, "Chest": 0, "Head": 0},  # VMC uses bone names, not IDs
        rotation_format="quaternion",
    ),
    "resonite": OSCProfile(
        name="Resonite",
        position_pattern="/avatar/parameters/OSCTracker{id}Position",
        rotation_pattern="/avatar/parameters/OSCTracker{id}Rotation",
        joint_ids={"Hips": 1, "LeftFoot": 2, "RightFoot": 3, "Chest": 4, "Head": 5},
        rotation_format="euler",
    ),
}


class OSCRemapper:
    """Remaps joint names to application-specific OSC addresses."""

    def __init__(self, profile_name: str = "vrchat"):
        self._profile: OSCProfile = DEFAULT_PROFILES.get(profile_name) or DEFAULT_PROFILES["vrchat"]
        if profile_name not in DEFAULT_PROFILES:
            logger.warning("Unknown profile '%s', using vrchat", profile_name)

    @property
    def profile(self) -> OSCProfile:
        return self._profile

    def get_position_address(self, joint_name: str) -> str | None:
        tracker_id = self._profile.joint_ids.get(joint_name)
        if tracker_id is None:
            return None
        return self._profile.position_pattern.format(id=tracker_id)

    def get_rotation_address(self, joint_name: str) -> str | None:
        tracker_id = self._profile.joint_ids.get(joint_name)
        if tracker_id is None:
            return None
        return self._profile.rotation_pattern.format(id=tracker_id)

    @staticmethod
    def list_profiles() -> list[str]:
        return list(DEFAULT_PROFILES.keys())

    @staticmethod
    def load_custom_profile(filepath: str | Path) -> OSCProfile | None:
        try:
            data = json.loads(Path(filepath).read_text(encoding="utf-8"))
            return OSCProfile(**data)
        except Exception as e:
            logger.error("Failed to load profile: %s", e)
            return None
