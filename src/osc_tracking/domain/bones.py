"""Canonical skeleton bone names.

Lives in the domain layer so :class:`osc_tracking.domain.values.BoneId`
can validate against it without reaching into the complementary-filter
(infrastructure) module. ``complementary_filter.JOINT_NAMES`` stays
around as a back-compat re-export so existing callers — and there are
many — continue to work unchanged.

Order matters: it matches the typical 8-tracker IMU layout (e.g.
HaritoraX2) plus ``Head`` from the camera pipeline. Consumers that
iterate this list rely on that order for SHM layout and OSC output.
"""

from __future__ import annotations

# IMU side provides: Hips, Chest, LeftFoot, RightFoot,
#                     LeftKnee, RightKnee, LeftElbow, RightElbow
# Camera provides:   Head (via MediaPipe face landmarks)
JOINT_NAMES: list[str] = [
    "Hips", "Chest", "Head",
    "LeftFoot", "RightFoot",
    "LeftKnee", "RightKnee",
    "LeftElbow", "RightElbow",
]
