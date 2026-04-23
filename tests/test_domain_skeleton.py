"""Tests for the Skeleton aggregate root.

The Skeleton aggregate owns per-joint state, the current tracking mode,
and the snapshot timestamp. Its public surface is the only sanctioned
way for the application and UI layers to observe a tracked frame.
"""

from __future__ import annotations

import time

import pytest
from scipy.spatial.transform import Rotation

from osc_tracking.complementary_filter import JOINT_NAMES
from osc_tracking.domain import BoneId, Confidence, Position3D
from osc_tracking.domain.skeleton import JointSnapshot, Skeleton
from osc_tracking.state_machine import TrackingMode


def test_empty_skeleton_constructs():
    s = Skeleton()
    assert s.mode == TrackingMode.FULL_OCCLUSION
    assert s.timestamp == 0.0
    assert s.joints == {}


def test_update_joint_adds_new_joint():
    s = Skeleton()
    s.update_joint(
        BoneId("Hips"),
        Position3D(1.0, 2.0, 3.0),
        Rotation.identity(),
        Confidence(0.8),
    )
    snap = s.get_joint(BoneId("Hips"))
    assert snap is not None
    assert snap.position == Position3D(1.0, 2.0, 3.0)
    assert float(snap.confidence) == 0.8


def test_update_joint_replaces_existing():
    s = Skeleton()
    hips = BoneId("Hips")
    s.update_joint(hips, Position3D(0, 0, 0), Rotation.identity(), Confidence(0.5))
    s.update_joint(hips, Position3D(1, 1, 1), Rotation.identity(), Confidence(0.9))
    snap = s.get_joint(hips)
    assert snap is not None
    assert snap.position == Position3D(1, 1, 1)
    assert float(snap.confidence) == 0.9


def test_get_joint_returns_none_when_absent():
    s = Skeleton()
    assert s.get_joint(BoneId("Hips")) is None


def test_set_mode_updates_mode():
    s = Skeleton()
    s.set_mode(TrackingMode.VISIBLE)
    assert s.mode == TrackingMode.VISIBLE


def test_set_timestamp_updates():
    s = Skeleton()
    now = time.monotonic()
    s.set_timestamp(now)
    assert s.timestamp == now


def test_snapshot_is_independent_of_source():
    """Snapshot must be a value copy — mutating source after snapshot
    must not affect the snapshot."""
    s = Skeleton()
    s.update_joint(
        BoneId("Hips"), Position3D(0, 0, 0), Rotation.identity(), Confidence(0.5)
    )
    snap = s.snapshot()

    # Mutate source
    s.update_joint(
        BoneId("Hips"), Position3D(9, 9, 9), Rotation.identity(), Confidence(0.9)
    )

    # Snapshot unchanged
    snap_hips = snap.joints[BoneId("Hips")]
    assert snap_hips.position == Position3D(0, 0, 0)


def test_snapshot_contains_all_joints():
    s = Skeleton()
    for name in JOINT_NAMES:
        s.update_joint(
            BoneId(name), Position3D(0, 0, 0), Rotation.identity(), Confidence(0.5)
        )
    snap = s.snapshot()
    assert len(snap.joints) == len(JOINT_NAMES)


def test_joint_snapshot_is_frozen():
    js = JointSnapshot(
        position=Position3D(0, 0, 0),
        rotation=Rotation.identity(),
        confidence=Confidence(0.5),
    )
    with pytest.raises((AttributeError, TypeError)):
        js.position = Position3D(9, 9, 9)  # type: ignore[misc]


def test_accepts_bone_id_or_string_for_get_joint():
    """Ergonomic: callers can pass either BoneId or a raw string."""
    s = Skeleton()
    s.update_joint(BoneId("Hips"), Position3D(1, 2, 3), Rotation.identity(), Confidence(0.5))
    assert s.get_joint("Hips") is not None
    assert s.get_joint(BoneId("Hips")) is not None


