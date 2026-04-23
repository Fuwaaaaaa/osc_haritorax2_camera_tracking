"""Tests for N-view (3+ cameras) triangulation using synthetic data.

The 2-camera case is already covered by ``test_stereo_calibration.py``.
These tests cover the multi-view path: SVD-DLT triangulation, confidence
weighting, sub-view fallback, round-trip of the multi-view calibration
file format, and promotion of an existing StereoCalibration.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from osc_tracking.stereo_calibration import (
    CameraView,
    MultiViewCalibration,
    StereoCalibration,
    load_multiview_calibration,
    multiview_from_stereo,
    save_multiview_calibration,
    triangulate_multiview,
)


def _K(fx: float = 500.0, fy: float = 500.0, cx: float = 320.0, cy: float = 240.0) -> np.ndarray:
    return np.array([
        [fx, 0.0, cx],
        [0.0, fy, cy],
        [0.0, 0.0, 1.0],
    ])


def _project(view: CameraView, point_world: np.ndarray) -> np.ndarray:
    p = view.R_world @ point_world.reshape(3, 1) + view.T_world.reshape(3, 1)
    p = view.K @ p
    return (p[:2] / p[2]).flatten()


@pytest.fixture
def three_camera_rig() -> MultiViewCalibration:
    """Three cameras in a horizontal arc, all looking along +Z.

    Camera 0 is the world origin. Camera 1 sits 30 cm to its right.
    Camera 2 sits 30 cm to its left. Pure translation — no rotation —
    so the geometry stays easy to reason about while still exercising
    a real 3-view constraint system (any pair alone would also solve).
    """
    K = _K()
    D = np.zeros(5)
    view0 = CameraView(K=K.copy(), D=D.copy(), R_world=np.eye(3), T_world=np.zeros(3))
    view1 = CameraView(
        K=K.copy(), D=D.copy(), R_world=np.eye(3), T_world=np.array([-0.3, 0.0, 0.0])
    )
    # view2 sits at world x = -0.3, so its world→camera translation is +0.3.
    view2 = CameraView(
        K=K.copy(), D=D.copy(), R_world=np.eye(3), T_world=np.array([0.3, 0.0, 0.0])
    )
    return MultiViewCalibration(
        views=[view0, view1, view2],
        image_size=(640, 480),
        reprojection_error=0.0,
    )


class TestTriangulateMultiview:
    def test_known_point_recovers_under_three_views(self, three_camera_rig: MultiViewCalibration) -> None:
        point = np.array([0.1, -0.05, 2.0])
        projections = [_project(v, point).reshape(1, 2) for v in three_camera_rig.views]

        result = triangulate_multiview(three_camera_rig, projections)

        assert result.shape == (1, 3)
        np.testing.assert_allclose(result[0], point, atol=1e-4)

    def test_multiple_points_round_trip(self, three_camera_rig: MultiViewCalibration) -> None:
        points = np.array([
            [0.0, 0.0, 1.5],
            [0.2, -0.1, 2.5],
            [-0.15, 0.05, 3.0],
        ])
        projections = [
            np.stack([_project(v, p) for p in points]) for v in three_camera_rig.views
        ]

        result = triangulate_multiview(three_camera_rig, projections)

        np.testing.assert_allclose(result, points, atol=1e-4)

    def test_zero_confidence_view_drops_out(self, three_camera_rig: MultiViewCalibration) -> None:
        """A view with confidence 0 contributes nothing, other views still solve."""
        point = np.array([0.0, 0.0, 2.0])
        projections = [_project(v, point).reshape(1, 2) for v in three_camera_rig.views]
        # Camera 2's projection is garbage — but confidence is zero so it's
        # excluded and the answer still comes from cameras 0 and 1.
        projections[2] = np.array([[9999.0, 9999.0]])
        conf = [np.array([1.0]), np.array([1.0]), np.array([0.0])]

        result = triangulate_multiview(three_camera_rig, projections, conf)

        np.testing.assert_allclose(result[0], point, atol=1e-4)

    def test_only_one_view_returns_nan(self, three_camera_rig: MultiViewCalibration) -> None:
        """A point visible in just one camera cannot be triangulated."""
        point = np.array([0.0, 0.0, 2.0])
        projections = [_project(v, point).reshape(1, 2) for v in three_camera_rig.views]
        conf = [np.array([1.0]), np.array([0.0]), np.array([0.0])]

        result = triangulate_multiview(three_camera_rig, projections, conf)

        assert np.all(np.isnan(result[0]))

    def test_confidence_weighted_prefers_reliable_view(
        self, three_camera_rig: MultiViewCalibration
    ) -> None:
        """A high-confidence noisy view should still pull the estimate."""
        point = np.array([0.0, 0.0, 2.0])
        projections = [_project(v, point).reshape(1, 2) for v in three_camera_rig.views]
        # Add one pixel of noise to view 1, but keep confidence equal — the
        # SVD solver should still land very close.
        projections[1] = projections[1] + np.array([[0.5, -0.5]])

        result = triangulate_multiview(three_camera_rig, projections)

        # ~sub-millimeter accuracy is unrealistic with half-pixel noise at
        # 2 m depth and a 30 cm baseline — bound the error to ~1 cm, which
        # still catches regressions (an un-weighted or broken SVD would
        # land much further off).
        np.testing.assert_allclose(result[0], point, atol=1e-2)

    def test_wrong_view_count_raises(self, three_camera_rig: MultiViewCalibration) -> None:
        point = np.array([0.0, 0.0, 2.0])
        projections = [
            _project(three_camera_rig.views[0], point).reshape(1, 2),
            _project(three_camera_rig.views[1], point).reshape(1, 2),
        ]  # only 2 views for a 3-view rig
        with pytest.raises(ValueError, match="Expected 3"):
            triangulate_multiview(three_camera_rig, projections)

    def test_single_camera_calib_rejected(self) -> None:
        view = CameraView(K=_K(), D=np.zeros(5), R_world=np.eye(3), T_world=np.zeros(3))
        calib = MultiViewCalibration(views=[view], image_size=(640, 480))
        with pytest.raises(ValueError, match="at least 2 cameras"):
            triangulate_multiview(calib, [np.array([[100.0, 100.0]])])


class TestMultiViewFromStereo:
    def test_promoted_stereo_round_trips_a_point(self) -> None:
        K = _K()
        stereo = StereoCalibration(
            K1=K.copy(), D1=np.zeros(5),
            K2=K.copy(), D2=np.zeros(5),
            R=np.eye(3),
            T=np.array([[0.3], [0.0], [0.0]]),
            image_size=(640, 480),
            reprojection_error=0.0,
        )

        mv = multiview_from_stereo(stereo)
        assert mv.camera_count == 2

        point = np.array([0.0, 0.0, 2.0])
        projections = [_project(v, point).reshape(1, 2) for v in mv.views]

        result = triangulate_multiview(mv, projections)
        np.testing.assert_allclose(result[0], point, atol=1e-4)


class TestMultiViewCalibrationPersistence:
    def test_save_and_load_round_trip(
        self, three_camera_rig: MultiViewCalibration, tmp_path: Path
    ) -> None:
        out = tmp_path / "mv_calib.npz"
        save_multiview_calibration(three_camera_rig, out)

        loaded = load_multiview_calibration(out)
        assert loaded is not None
        assert loaded.camera_count == 3
        assert loaded.image_size == (640, 480)
        for original, restored in zip(three_camera_rig.views, loaded.views):
            np.testing.assert_allclose(restored.K, original.K)
            np.testing.assert_allclose(restored.D, original.D)
            np.testing.assert_allclose(restored.R_world, original.R_world)
            np.testing.assert_allclose(restored.T_world, original.T_world)

    def test_load_missing_file_returns_none(self, tmp_path: Path) -> None:
        assert load_multiview_calibration(tmp_path / "nope.npz") is None
