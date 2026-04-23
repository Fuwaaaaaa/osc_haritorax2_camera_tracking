"""Domain layer — pure, I/O-free types and logic.

The domain layer holds the business vocabulary: value objects, the
Skeleton aggregate, domain events, and any logic that only depends on
those types. Nothing in this package may import from ``camera_tracker``,
``osc_receiver``, UI modules, or anything that touches the filesystem
or network.

Public surface re-exported from submodules so callers can write
``from osc_tracking.domain import Position3D`` instead of drilling into
the module path.
"""

from osc_tracking.domain.modes import TrackingMode
from osc_tracking.domain.skeleton import JointSnapshot, Skeleton, SkeletonSnapshot
from osc_tracking.domain.values import BoneId, Confidence, Position3D

__all__ = [
    "BoneId",
    "Confidence",
    "JointSnapshot",
    "Position3D",
    "Skeleton",
    "SkeletonSnapshot",
    "TrackingMode",
]
