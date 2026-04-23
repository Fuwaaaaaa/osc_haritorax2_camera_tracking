"""Tests for domain value objects.

Value Objects are immutable and equality is value-based. They carry
invariants that the type system alone cannot express (a Confidence is
always in [0, 1]; a BoneId is always a valid skeleton joint name).
"""

from __future__ import annotations

import numpy as np
import pytest

from osc_tracking.domain.values import BoneId, Confidence, Position3D

# ---------- Position3D ----------

class TestPosition3D:
    def test_constructs_from_three_floats(self):
        p = Position3D(1.0, 2.0, 3.0)
        assert p.x == 1.0
        assert p.y == 2.0
        assert p.z == 3.0

    def test_value_equality(self):
        assert Position3D(1.0, 2.0, 3.0) == Position3D(1.0, 2.0, 3.0)

    def test_different_values_not_equal(self):
        assert Position3D(1.0, 2.0, 3.0) != Position3D(1.0, 2.0, 3.1)

    def test_immutable_fields(self):
        """Value Objects must be frozen — reassignment must raise."""
        p = Position3D(1.0, 2.0, 3.0)
        with pytest.raises((AttributeError, TypeError)):
            p.x = 99.0  # type: ignore[misc]

    def test_from_array_roundtrip(self):
        arr = np.array([1.5, -2.0, 3.25])
        p = Position3D.from_array(arr)
        back = p.to_array()
        assert np.allclose(back, arr)

    def test_rejects_nan(self):
        with pytest.raises(ValueError, match="finite"):
            Position3D(float("nan"), 0.0, 0.0)

    def test_rejects_inf(self):
        with pytest.raises(ValueError, match="finite"):
            Position3D(0.0, float("inf"), 0.0)

    def test_from_array_rejects_wrong_shape(self):
        with pytest.raises(ValueError):
            Position3D.from_array(np.array([1.0, 2.0]))  # 2-D not allowed


# ---------- Confidence ----------

class TestConfidence:
    def test_constructs_in_range(self):
        c = Confidence(0.5)
        assert float(c) == 0.5

    def test_boundary_zero_accepted(self):
        assert float(Confidence(0.0)) == 0.0

    def test_boundary_one_accepted(self):
        assert float(Confidence(1.0)) == 1.0

    def test_rejects_below_zero(self):
        with pytest.raises(ValueError, match="\\[0"):
            Confidence(-0.01)

    def test_rejects_above_one(self):
        with pytest.raises(ValueError, match="1"):
            Confidence(1.01)

    def test_rejects_nan(self):
        with pytest.raises(ValueError):
            Confidence(float("nan"))

    def test_equality_by_value(self):
        assert Confidence(0.7) == Confidence(0.7)
        assert Confidence(0.7) != Confidence(0.8)

    def test_comparison_operators(self):
        """Confidence supports ordering — threshold checks read naturally."""
        assert Confidence(0.3) < Confidence(0.7)
        assert Confidence(0.7) > Confidence(0.3)
        assert Confidence(0.5) <= Confidence(0.5)


# ---------- BoneId ----------

class TestBoneId:
    def test_accepts_all_valid_joint_names(self):
        from osc_tracking.complementary_filter import JOINT_NAMES
        for name in JOINT_NAMES:
            b = BoneId(name)
            assert str(b) == name

    def test_rejects_unknown_name(self):
        with pytest.raises(ValueError, match="unknown bone"):
            BoneId("nose")  # not in JOINT_NAMES

    def test_rejects_empty_string(self):
        with pytest.raises(ValueError):
            BoneId("")

    def test_equality_by_value(self):
        assert BoneId("Hips") == BoneId("Hips")
        assert BoneId("Hips") != BoneId("Chest")

    def test_hashable(self):
        """BoneId must be usable as a dict key."""
        d = {BoneId("Hips"): 1, BoneId("Chest"): 2}
        assert d[BoneId("Hips")] == 1

    def test_all_returns_every_canonical_bone(self):
        """BoneId.all() must mirror JOINT_NAMES."""
        from osc_tracking.complementary_filter import JOINT_NAMES
        bones = BoneId.all()
        assert [b.name for b in bones] == list(JOINT_NAMES)
        assert all(isinstance(b, BoneId) for b in bones)
