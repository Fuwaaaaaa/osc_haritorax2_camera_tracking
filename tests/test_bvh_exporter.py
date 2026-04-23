"""Tests for the BVH motion capture exporter.

Writes to ``tmp_path``, reads the result back, and asserts on the BVH
hierarchy + motion sections. Format details: http://www.cs.man.ac.uk/~toby/writing/PRML/bvh.html
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from osc_tracking.bvh_exporter import BVH_HIERARCHY, BVHExporter


def _identity_frame() -> dict[str, tuple[np.ndarray, Rotation]]:
    return {
        name: (np.array([0.0, 0.0, 0.0]), Rotation.identity())
        for name in BVH_HIERARCHY
    }


def test_constructor_defaults_to_30_fps():
    exp = BVHExporter()
    assert exp.fps == 30.0
    assert exp.frame_count == 0


def test_add_frame_accumulates_frames():
    exp = BVHExporter()
    exp.add_frame(_identity_frame())
    exp.add_frame(_identity_frame())
    assert exp.frame_count == 2


def test_clear_resets_frame_buffer():
    exp = BVHExporter()
    exp.add_frame(_identity_frame())
    exp.clear()
    assert exp.frame_count == 0


def test_export_writes_hierarchy_section(tmp_path):
    exp = BVHExporter()
    exp.add_frame(_identity_frame())
    path = tmp_path / "out.bvh"
    count = exp.export(path)
    text = path.read_text()

    assert count == 1
    # HIERARCHY section is present and starts at root.
    assert text.startswith("HIERARCHY\n")
    assert "ROOT Hips" in text
    # Every canonical bone appears as JOINT or ROOT.
    for bone in BVH_HIERARCHY:
        assert bone in text
    # Root has 6 channels (pos + rot), joints have 3 (rot only).
    assert "CHANNELS 6 Xposition Yposition Zposition" in text
    assert "CHANNELS 3 Zrotation Xrotation Yrotation" in text


def test_export_writes_motion_section_with_frame_count(tmp_path):
    exp = BVHExporter(fps=60.0)
    for _ in range(5):
        exp.add_frame(_identity_frame())
    path = tmp_path / "motion.bvh"
    exp.export(path)
    text = path.read_text()

    assert "MOTION" in text
    assert "Frames: 5" in text
    # Frame time = 1/60 at 60 fps
    assert "Frame Time: 0.016667" in text
    # Motion data lines: 5 lines after "Frame Time: ..." header.
    motion = text.split("MOTION\n", 1)[1]
    motion_lines = [ln for ln in motion.splitlines() if ln and not ln.startswith(("Frames:", "Frame Time"))]
    assert len(motion_lines) == 5


def test_export_hips_has_position_and_rotation_floats(tmp_path):
    """Root frame row includes 6 numbers (pos xyz + rot zxy) plus 3 per
    other bone."""
    exp = BVHExporter()
    frame = _identity_frame()
    # Offset Hips so we can detect the position columns.
    frame["Hips"] = (np.array([0.5, 1.0, 1.5]), Rotation.identity())
    exp.add_frame(frame)
    path = tmp_path / "pos.bvh"
    exp.export(path)
    text = path.read_text()

    motion = text.split("MOTION\n", 1)[1].splitlines()
    # First data row.
    data_row = next(ln for ln in motion if ln.replace(".", "").replace("-", "").replace(" ", "").isdigit())
    numbers = data_row.split()
    # 6 root values + 3 per non-root bone (8 others) = 6 + 24 = 30
    expected_count = 6 + 3 * (len(BVH_HIERARCHY) - 1)
    assert len(numbers) == expected_count
    # Hips position was (0.5, 1.0, 1.5) meters → BVH uses cm (x100).
    assert float(numbers[0]) == pytest.approx(50.0, abs=1e-3)
    assert float(numbers[1]) == pytest.approx(100.0, abs=1e-3)
    assert float(numbers[2]) == pytest.approx(150.0, abs=1e-3)


def test_export_fills_missing_joint_with_zeros(tmp_path):
    """If a frame lacks a joint, its row should contribute zero rotation,
    not crash."""
    exp = BVHExporter()
    # Provide only Hips; other joints missing.
    exp.add_frame({"Hips": (np.array([0, 0, 0]), Rotation.identity())})
    path = tmp_path / "partial.bvh"
    count = exp.export(path)
    assert count == 1
    # File must be valid and parseable.
    text = path.read_text()
    assert "MOTION" in text


def test_export_creates_parent_directories(tmp_path):
    exp = BVHExporter()
    exp.add_frame(_identity_frame())
    nested = tmp_path / "deep" / "nested" / "path" / "out.bvh"
    exp.export(nested)
    assert nested.exists()


def test_export_with_zero_frames_still_writes_header(tmp_path):
    exp = BVHExporter()
    path = tmp_path / "empty.bvh"
    count = exp.export(path)
    assert count == 0
    text = path.read_text()
    assert "HIERARCHY" in text
    assert "Frames: 0" in text


def test_hierarchy_shape_is_tree_rooted_at_hips():
    """Sanity: every bone except Hips has a parent that is itself in
    the hierarchy."""
    for bone, info in BVH_HIERARCHY.items():
        if bone == "Hips":
            assert info["parent"] is None
        else:
            assert info["parent"] in BVH_HIERARCHY
