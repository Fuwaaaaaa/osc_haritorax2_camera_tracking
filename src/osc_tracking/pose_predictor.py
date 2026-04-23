"""Pose prediction for occluded / missing joint data.

During ``FULL_OCCLUSION`` or ``PARTIAL_OCCLUSION`` the camera tracker
produces no fresh position for some joints. Instead of freezing on the
last observed position (which shows as a rubber-banded skeleton when
the user re-enters view), the fusion engine consults a predictor for a
short-horizon extrapolation.

Design
------
:class:`PosePredictor` is a ``@runtime_checkable`` Protocol so callers
stay decoupled from the concrete predictor. Today's implementation is
:class:`VelocityPredictor` — a simple per-joint linear-velocity model
computed over a rolling history window. The TODO "deep-learning pose
prediction" becomes a future drop-in replacement of this same Protocol
(e.g. a small LSTM that trains on recorded sessions).

Why not a full Kalman filter? Kalman adds a second tuning surface
(process / measurement noise) that duplicates what
:mod:`complementary_filter` already does. Linear extrapolation covers
the 100-300 ms typical occlusion window cleanly; for longer gaps the
``stale_window_seconds`` guard drops the predictor back to "hold last
position", which is the safe default.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class PosePredictor(Protocol):
    """Short-horizon position predictor for a skeleton joint."""

    def observe(self, joint_name: str, position: np.ndarray, t: float) -> None:
        """Record an observed position at time ``t`` (monotonic seconds)."""
        ...

    def predict(self, joint_name: str, t: float | None = None) -> np.ndarray | None:
        """Return the predicted position at time ``t``.

        If ``t`` is ``None``, the predictor returns the last observed
        position (safe fallback for callers that don't care about the
        extrapolation horizon).
        """
        ...

    def reset(self, joint_name: str) -> None:
        """Discard history for one joint."""
        ...

    def reset_all(self) -> None:
        """Discard history for every joint."""
        ...


@dataclass
class _Sample:
    position: np.ndarray
    t: float


@dataclass
class _JointHistory:
    samples: deque[_Sample] = field(default_factory=lambda: deque())


class VelocityPredictor:
    """Linear-velocity predictor with per-joint rolling history.

    Parameters
    ----------
    max_history
        Number of recent samples retained per joint. Larger windows smooth
        the velocity estimate; smaller windows react faster to direction
        changes. Default 5 balances both over the 100-300 ms occlusion
        window we care about.
    stale_window_seconds
        If no new observation arrives within this window, the history is
        cleared the next time a sample comes in. Prevents teleporting
        after the user re-enters camera view following a long occlusion.
    max_predict_seconds
        Upper bound on the extrapolation horizon relative to the most
        recent sample. A camera outage of 5 seconds should not produce a
        5-second extrapolation at some velocity — the skeleton would end
        up in another room.
    """

    def __init__(
        self,
        max_history: int = 5,
        stale_window_seconds: float = 1.0,
        max_predict_seconds: float = 2.0,
    ) -> None:
        if max_history < 2:
            raise ValueError("max_history must be >= 2 to estimate velocity")
        self.max_history = int(max_history)
        self.stale_window_seconds = float(stale_window_seconds)
        self.max_predict_seconds = float(max_predict_seconds)
        self._joints: dict[str, _JointHistory] = {}

    def observe(self, joint_name: str, position: np.ndarray, t: float) -> None:
        pos = np.asarray(position, dtype=float).reshape(3)
        if not np.all(np.isfinite(pos)):
            return

        history = self._joints.get(joint_name)
        if history is None:
            history = _JointHistory()
            self._joints[joint_name] = history

        if history.samples:
            gap = t - history.samples[-1].t
            if gap > self.stale_window_seconds:
                history.samples.clear()

        history.samples.append(_Sample(position=pos.copy(), t=float(t)))
        while len(history.samples) > self.max_history:
            history.samples.popleft()

    def predict(
        self, joint_name: str, t: float | None = None
    ) -> np.ndarray | None:
        history = self._joints.get(joint_name)
        if history is None or not history.samples:
            return None

        last = history.samples[-1]
        if t is None or len(history.samples) < 2:
            return np.asarray(last.position.copy())

        first = history.samples[0]
        span = last.t - first.t
        if span <= 0:
            return np.asarray(last.position.copy())
        velocity = (last.position - first.position) / span

        horizon = min(t - last.t, self.max_predict_seconds)
        if horizon <= 0:
            return np.asarray(last.position.copy())
        return np.asarray(last.position + velocity * horizon)

    def reset(self, joint_name: str) -> None:
        self._joints.pop(joint_name, None)

    def reset_all(self) -> None:
        self._joints.clear()
