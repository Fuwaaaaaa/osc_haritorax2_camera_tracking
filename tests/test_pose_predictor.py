"""Unit tests for the pose predictor.

Predictors are pure-function style components with an internal rolling
history. Tests avoid any camera / subprocess machinery; they feed joint
positions directly and assert the predicted positions.
"""

from __future__ import annotations

import numpy as np
import pytest

from osc_tracking.pose_predictor import (
    PosePredictor,
    VelocityPredictor,
)

# ---------- protocol conformance ----------

def test_velocity_predictor_conforms_to_protocol():
    p = VelocityPredictor()
    assert isinstance(p, PosePredictor)


# ---------- observe / predict basics ----------

def test_predict_returns_none_before_any_observation():
    p = VelocityPredictor()
    assert p.predict("Hips") is None


def test_predict_returns_last_position_after_single_observation():
    """With one sample there's no velocity yet — predictor should hold
    the last position rather than extrapolating wildly."""
    p = VelocityPredictor()
    p.observe("Hips", np.array([1.0, 2.0, 3.0]), t=0.0)
    pred = p.predict("Hips")
    assert pred is not None
    assert np.allclose(pred, [1.0, 2.0, 3.0])


def test_predict_extrapolates_from_two_observations():
    """Linear velocity from two samples gives the next predicted step."""
    p = VelocityPredictor()
    p.observe("Hips", np.array([0.0, 0.0, 0.0]), t=0.0)
    p.observe("Hips", np.array([1.0, 0.0, 0.0]), t=1.0)
    # At t=2.0 (1 second after last), velocity=(1,0,0)/s → predicted (2,0,0)
    pred = p.predict("Hips", t=2.0)
    assert pred is not None
    assert np.allclose(pred, [2.0, 0.0, 0.0], atol=1e-6)


def test_predict_with_no_time_argument_uses_last_observed_position():
    """Without a timestamp, predict() returns the last known position —
    a safe default for callers that just want 'what should we send?'."""
    p = VelocityPredictor()
    p.observe("Hips", np.array([0.0, 0.0, 0.0]), t=0.0)
    p.observe("Hips", np.array([1.0, 2.0, 3.0]), t=0.1)
    pred = p.predict("Hips")
    assert pred is not None
    assert np.allclose(pred, [1.0, 2.0, 3.0])


# ---------- per-joint independence ----------

def test_observing_one_joint_does_not_leak_into_another():
    p = VelocityPredictor()
    p.observe("Hips", np.array([1.0, 0.0, 0.0]), t=0.0)
    assert p.predict("Chest") is None


def test_multiple_joints_tracked_independently():
    p = VelocityPredictor()
    p.observe("Hips", np.array([0.0, 0.0, 0.0]), t=0.0)
    p.observe("Hips", np.array([1.0, 0.0, 0.0]), t=1.0)
    p.observe("Chest", np.array([0.0, 0.0, 0.0]), t=0.0)
    p.observe("Chest", np.array([0.0, 2.0, 0.0]), t=1.0)

    hips = p.predict("Hips", t=2.0)
    chest = p.predict("Chest", t=2.0)
    assert np.allclose(hips, [2.0, 0.0, 0.0], atol=1e-6)
    assert np.allclose(chest, [0.0, 4.0, 0.0], atol=1e-6)


# ---------- NaN / invalid input handling ----------

def test_observe_rejects_nan_position():
    """A NaN position must not corrupt the buffer."""
    p = VelocityPredictor()
    p.observe("Hips", np.array([np.nan, 0.0, 0.0]), t=0.0)
    assert p.predict("Hips") is None


def test_observe_rejects_inf_position():
    p = VelocityPredictor()
    p.observe("Hips", np.array([np.inf, 0.0, 0.0]), t=0.0)
    assert p.predict("Hips") is None


def test_predict_clamped_on_absurd_extrapolation_distance():
    """Extrapolation very far past the last sample should not drift to
    arbitrary positions — velocity should saturate."""
    p = VelocityPredictor(max_predict_seconds=0.5)
    p.observe("Hips", np.array([0.0, 0.0, 0.0]), t=0.0)
    p.observe("Hips", np.array([1.0, 0.0, 0.0]), t=0.1)
    # Velocity is 10 m/s; extrapolating 10 seconds would give 100m.
    # With max_predict_seconds=0.5, prediction caps at t = 0.1 + 0.5 = 0.6
    # → position = 0 + 10 * 0.6 = 6.0
    pred = p.predict("Hips", t=10.0)
    assert pred is not None
    assert pred[0] == pytest.approx(6.0, abs=1e-6)


# ---------- staleness / reset ----------

def test_reset_clears_history_for_joint():
    p = VelocityPredictor()
    p.observe("Hips", np.array([0.0, 0.0, 0.0]), t=0.0)
    p.observe("Hips", np.array([1.0, 0.0, 0.0]), t=1.0)
    p.reset("Hips")
    assert p.predict("Hips") is None


def test_reset_all_clears_every_joint():
    p = VelocityPredictor()
    p.observe("Hips", np.array([0.0, 0.0, 0.0]), t=0.0)
    p.observe("Chest", np.array([0.0, 0.0, 0.0]), t=0.0)
    p.reset_all()
    assert p.predict("Hips") is None
    assert p.predict("Chest") is None


def test_stale_history_auto_resets_after_gap():
    """If we don't observe for longer than stale_window_seconds, the
    previous velocity must be discarded — otherwise a resume after
    occlusion will teleport the skeleton."""
    p = VelocityPredictor(stale_window_seconds=1.0)
    p.observe("Hips", np.array([0.0, 0.0, 0.0]), t=0.0)
    p.observe("Hips", np.array([1.0, 0.0, 0.0]), t=0.1)
    # Fresh sample 2 seconds later — the prior velocity is stale
    p.observe("Hips", np.array([5.0, 0.0, 0.0]), t=2.5)
    # Next prediction at t=2.6 should NOT extrapolate from the old velocity
    # (which would have given something in the hundreds). With history
    # reset, the single new sample is held at its observed position.
    pred = p.predict("Hips", t=2.6)
    assert pred is not None
    assert np.allclose(pred, [5.0, 0.0, 0.0], atol=1e-6)


# ---------- history window ----------

def test_history_window_bounded():
    """With max_history=3, older samples roll off so velocity reflects
    recent motion, not the full session."""
    p = VelocityPredictor(max_history=3)
    # First few samples: slow motion
    for i in range(5):
        p.observe("Hips", np.array([0.1 * i, 0.0, 0.0]), t=float(i))
    # Now fast motion
    for i in range(5, 8):
        p.observe("Hips", np.array([float(i), 0.0, 0.0]), t=float(i))

    # With max_history=3, only the last 3 samples (t=5,6,7 with x=5,6,7)
    # inform velocity. Velocity = 1.0 m/s; if the old slow samples were
    # still in history, velocity would be far lower.
    pred = p.predict("Hips", t=7.5)
    assert pred is not None
    # Linear extrap at +0.5s: x = 7 + 1.0 * 0.5 = 7.5
    assert pred[0] == pytest.approx(7.5, abs=0.01)
