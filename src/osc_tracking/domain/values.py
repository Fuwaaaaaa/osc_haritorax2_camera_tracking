"""Value Objects — immutable, equality-by-value domain primitives.

Every type in this module is ``@dataclass(frozen=True)`` (or equivalent)
and validates its invariants at construction. Using these in signatures
replaces ad-hoc ``float`` / ``np.ndarray`` / ``str`` parameters and
catches whole categories of bugs at the boundary instead of deep in a
filter loop (e.g. "is this a confidence or a probability?",
"is this a pixel position or a world-space one?").

These types are deliberately small and cheap to construct. Treat them
as "named floats / tuples" rather than heavy wrappers.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import total_ordering

import numpy as np


@dataclass(frozen=True, slots=True)
class Position3D:
    """World-space 3D position in meters (x right, y up, z forward).

    Immutable. Constructed values are guaranteed finite — NaN and inf
    are rejected at the boundary so downstream code does not have to
    guard repeatedly.
    """

    x: float
    y: float
    z: float

    def __post_init__(self) -> None:
        for name, value in (("x", self.x), ("y", self.y), ("z", self.z)):
            if not np.isfinite(value):
                raise ValueError(f"Position3D.{name} must be finite, got {value}")

    @classmethod
    def from_array(cls, arr: np.ndarray) -> Position3D:
        """Build from a length-3 numpy array. Shape is validated."""
        if arr.shape != (3,):
            raise ValueError(f"Position3D.from_array expects shape (3,), got {arr.shape}")
        return cls(float(arr[0]), float(arr[1]), float(arr[2]))

    def to_array(self) -> np.ndarray:
        """Return a fresh (3,) numpy array — callers may mutate freely."""
        return np.array([self.x, self.y, self.z], dtype=float)


@total_ordering
@dataclass(frozen=True, slots=True)
class Confidence:
    """A confidence / weight in the closed interval [0, 1].

    Comparable so threshold checks read as ``conf >= partial_threshold``.
    The ``@total_ordering`` decorator fills in the remaining ops from
    ``__eq__`` and ``__lt__``.
    """

    value: float

    def __post_init__(self) -> None:
        v = self.value
        if not np.isfinite(v):
            raise ValueError(f"Confidence must be finite, got {v}")
        if v < 0.0 or v > 1.0:
            raise ValueError(f"Confidence must be in [0, 1], got {v}")

    def __float__(self) -> float:
        return self.value

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Confidence):
            return NotImplemented
        return self.value < other.value


@dataclass(frozen=True, slots=True)
class BoneId:
    """Canonical skeleton bone identifier.

    Validated against :data:`osc_tracking.domain.bones.JOINT_NAMES` at
    construction so typos surface at the boundary rather than as a
    silently-missing dict key deep in the fusion loop.
    """

    name: str

    def __post_init__(self) -> None:
        from osc_tracking.domain.bones import JOINT_NAMES
        if not self.name:
            raise ValueError("BoneId cannot be empty")
        if self.name not in JOINT_NAMES:
            raise ValueError(
                f"unknown bone {self.name!r}; valid names: {sorted(JOINT_NAMES)}"
            )

    def __str__(self) -> str:
        return self.name

    @classmethod
    def all(cls) -> list[BoneId]:
        """Return every canonical bone, in skeleton order.

        Convenience for callers that used to iterate ``JOINT_NAMES``
        directly — prefer this when you need strongly-typed ids instead
        of bare strings.
        """
        from osc_tracking.domain.bones import JOINT_NAMES
        return [cls(name) for name in JOINT_NAMES]
