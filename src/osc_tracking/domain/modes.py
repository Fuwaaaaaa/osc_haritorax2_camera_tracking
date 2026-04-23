"""Tracking mode enum — pure domain type.

Lives in the domain layer so aggregates like :class:`Skeleton` can
reference the current mode without pulling in the infrastructure-level
state machine.
"""

from __future__ import annotations

from enum import Enum, auto


class TrackingMode(Enum):
    VISIBLE = auto()
    PARTIAL_OCCLUSION = auto()
    FULL_OCCLUSION = auto()
    IMU_DISCONNECTED = auto()
    SINGLE_CAM_DEGRADED = auto()
    FUTON_MODE = auto()
