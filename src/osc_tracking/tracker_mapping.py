"""Shared tracker name mappings for IMU receivers.

Single source of truth that maps the 8-tracker IMU body layout (used by
HaritoraX2 and mirrored by SlimeVR Server OSC output) to the skeleton
joint names used in ``complementary_filter.JOINT_NAMES``.

Two receiver-specific views are exposed:

- ``HARITORA_NATIVE_TO_SKELETON``: HaritoraX2 native label strings
  (e.g. ``"hip"``, ``"leftAnkle"``) -> skeleton joint name.
- ``SLIMEVR_OSC_INDEX_TO_SKELETON``: SlimeVR Server OSC tracker index
  (1-8) -> skeleton joint name.

Both maps describe the same eight physical tracker slots in the same
order, so any receiver can round-trip through either key style.
"""

from __future__ import annotations

# HaritoraX2 native label (as advertised / assigned by the device firmware)
# mapped to the skeleton joint name used throughout this project.
HARITORA_NATIVE_TO_SKELETON: dict[str, str] = {
    "hip": "Hips",
    "chest": "Chest",
    "leftAnkle": "LeftFoot",
    "rightAnkle": "RightFoot",
    "leftKnee": "LeftKnee",
    "rightKnee": "RightKnee",
    "leftElbow": "LeftElbow",
    "rightElbow": "RightElbow",
}

# SlimeVR Server's OSC output assigns tracker indices 1..8 to these roles
# in the order below. Matches the shipped SlimeTora+SlimeVR configuration
# that routes HaritoraX2 through SlimeVR Server.
SLIMEVR_OSC_INDEX_TO_SKELETON: dict[int, str] = {
    1: "Hips",
    2: "Chest",
    3: "LeftFoot",
    4: "RightFoot",
    5: "LeftKnee",
    6: "RightKnee",
    7: "LeftElbow",
    8: "RightElbow",
}


def slimevr_osc_addresses() -> dict[str, str]:
    """Return the OSC address pattern -> skeleton joint name mapping.

    Mirrors the historical ``OSCReceiver.DEFAULT_BONE_ADDRESSES`` constant
    so the OSC receiver and BLE receiver share one tracker roster.
    """
    return {
        f"/tracking/trackers/{idx}/rotation": bone
        for idx, bone in SLIMEVR_OSC_INDEX_TO_SKELETON.items()
    }
