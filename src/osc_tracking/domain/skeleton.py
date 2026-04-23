"""Skeleton aggregate root.

The Skeleton owns per-joint state (position / rotation / confidence),
the current tracking mode, and the frame timestamp. It is the single
source of truth passed between the application layer (FusionEngine)
and the interface-adapter layer (subsystems: senders, dashboard, etc).

Design notes
------------
- :class:`Skeleton` is mutable: the fusion loop calls
  :meth:`update_joint` / :meth:`set_mode` every frame. Consumers that
  need a stable reference take a :meth:`snapshot`, which returns an
  immutable :class:`SkeletonSnapshot` with frozen :class:`JointSnapshot`
  entries.
- Equality and hashing are not defined on :class:`Skeleton` — two
  skeletons with the same joints at the same frame are *not* considered
  equal; aggregates are identity types, not value types.
"""

from __future__ import annotations

from dataclasses import dataclass

from scipy.spatial.transform import Rotation

from osc_tracking.domain.modes import TrackingMode
from osc_tracking.domain.values import BoneId, Confidence, Position3D


@dataclass(frozen=True, slots=True)
class JointSnapshot:
    """Immutable per-joint state at a single moment."""

    position: Position3D
    rotation: Rotation
    confidence: Confidence


@dataclass(frozen=True, slots=True)
class SkeletonSnapshot:
    """Immutable frame snapshot.

    The ``joints`` dict is a fresh copy at snapshot time; mutating the
    source Skeleton afterwards does not affect this snapshot.
    """

    joints: dict[BoneId, JointSnapshot]
    mode: TrackingMode
    timestamp: float


class Skeleton:
    """Aggregate root for the tracked skeleton.

    The fusion engine updates joints and mode each cycle. UI / output
    subsystems observe the skeleton through :meth:`snapshot` so they
    see a consistent frame regardless of when the fusion loop writes
    next.
    """

    def __init__(self) -> None:
        self._joints: dict[BoneId, JointSnapshot] = {}
        self._mode: TrackingMode = TrackingMode.FULL_OCCLUSION
        self._timestamp: float = 0.0

    # ---- write surface ----

    def update_joint(
        self,
        bone: BoneId,
        position: Position3D,
        rotation: Rotation,
        confidence: Confidence,
    ) -> None:
        self._joints[bone] = JointSnapshot(
            position=position,
            rotation=rotation,
            confidence=confidence,
        )

    def set_mode(self, mode: TrackingMode) -> None:
        self._mode = mode

    def set_timestamp(self, ts: float) -> None:
        self._timestamp = float(ts)

    # ---- read surface ----

    @property
    def joints(self) -> dict[BoneId, JointSnapshot]:
        """Direct joint view. Use :meth:`snapshot` when you need a
        stable copy."""
        return self._joints

    @property
    def mode(self) -> TrackingMode:
        return self._mode

    @property
    def timestamp(self) -> float:
        return self._timestamp

    def get_joint(self, bone: BoneId | str) -> JointSnapshot | None:
        key = bone if isinstance(bone, BoneId) else BoneId(bone)
        return self._joints.get(key)

    def snapshot(self) -> SkeletonSnapshot:
        """Return an immutable copy of the current frame."""
        return SkeletonSnapshot(
            joints=dict(self._joints),
            mode=self._mode,
            timestamp=self._timestamp,
        )
