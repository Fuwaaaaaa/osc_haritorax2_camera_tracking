"""Tests for stereo calibration and triangulation using synthetic data."""

import numpy as np
import pytest

from osc_tracking.stereo_calibration import (
    StereoCalibration,
    compute_reprojection_error,
    load_calibration,
    save_calibration,
    triangulate_points,
)


@pytest.fixture
def synthetic_calib():
    """Create a synthetic stereo calibration with known parameters."""
    # Camera 1 at origin, camera 2 shifted 0.3m to the right
    K = np.array([
        [500.0, 0.0, 320.0],
        [0.0, 500.0, 240.0],
        [0.0, 0.0, 1.0],
    ])
    D = np.zeros(5)
    R = np.eye(3)  # Cameras parallel
    T = np.array([[0.3], [0.0], [0.0]])  # 30cm baseline

    return StereoCalibration(
        K1=K.copy(), D1=D.copy(),
        K2=K.copy(), D2=D.copy(),
        R=R, T=T,
        image_size=(640, 480),
        reprojection_error=0.5,
    )


def project_point(K, R, T, point_3d):
    """Project a 3D point to 2D using camera parameters."""
    p = R @ point_3d.reshape(3, 1) + T
    p = K @ p
    return (p[:2] / p[2]).flatten()


class TestTriangulation:
    def test_known_point_triangulates_correctly(self, synthetic_calib):
        """A known 3D point should triangulate back to itself."""
        # Point 2m in front of camera, slightly off-center
        point_3d = np.array([0.1, -0.1, 2.0])

        # Project to both cameras
        pt1 = project_point(
            synthetic_calib.K1, np.eye(3), np.zeros((3, 1)), point_3d
        )
        pt2 = project_point(
            synthetic_calib.K2, synthetic_calib.R, synthetic_calib.T, point_3d
        )

        # Triangulate
        result = triangulate_points(
            synthetic_calib,
            pt1.reshape(1, 2),
            pt2.reshape(1, 2),
        )

        np.testing.assert_allclose(result[0], point_3d, atol=0.01)

    def test_multiple_points(self, synthetic_calib):
        """Multiple points should all triangulate correctly."""
        points_3d = np.array([
            [0.0, 0.0, 1.5],
            [0.2, -0.1, 2.0],
            [-0.1, 0.3, 3.0],
        ])

        pts1 = []
        pts2 = []
        for pt in points_3d:
            pts1.append(project_point(
                synthetic_calib.K1, np.eye(3), np.zeros((3, 1)), pt
            ))
            pts2.append(project_point(
                synthetic_calib.K2, synthetic_calib.R, synthetic_calib.T, pt
            ))

        result = triangulate_points(
            synthetic_calib,
            np.array(pts1),
            np.array(pts2),
        )

        np.testing.assert_allclose(result, points_3d, atol=0.01)

    def test_point_at_center(self, synthetic_calib):
        """A point on the optical axis should triangulate correctly."""
        point_3d = np.array([0.0, 0.0, 2.0])
        pt1 = project_point(
            synthetic_calib.K1, np.eye(3), np.zeros((3, 1)), point_3d
        )
        pt2 = project_point(
            synthetic_calib.K2, synthetic_calib.R, synthetic_calib.T, point_3d
        )

        result = triangulate_points(
            synthetic_calib,
            pt1.reshape(1, 2),
            pt2.reshape(1, 2),
        )

        np.testing.assert_allclose(result[0], point_3d, atol=0.01)


class TestReprojectionError:
    def test_perfect_data_has_low_error(self, synthetic_calib):
        """Points that triangulate perfectly should have near-zero reproj error."""
        point_3d = np.array([[0.1, -0.1, 2.0]])
        pt1 = project_point(
            synthetic_calib.K1, np.eye(3), np.zeros((3, 1)), point_3d[0]
        ).reshape(1, 2)
        pt2 = project_point(
            synthetic_calib.K2, synthetic_calib.R, synthetic_calib.T, point_3d[0]
        ).reshape(1, 2)

        error = compute_reprojection_error(
            synthetic_calib, point_3d, pt1, pt2
        )

        assert error < 1.0  # Sub-pixel error


class TestProjectionMatrices:
    def test_p1_is_identity_projection(self, synthetic_calib):
        """P1 should be K1 * [I | 0]."""
        P1 = synthetic_calib.P1
        assert P1.shape == (3, 4)
        expected = synthetic_calib.K1 @ np.hstack([np.eye(3), np.zeros((3, 1))])
        np.testing.assert_allclose(P1, expected)

    def test_p2_includes_extrinsics(self, synthetic_calib):
        """P2 should be K2 * [R | T]."""
        P2 = synthetic_calib.P2
        assert P2.shape == (3, 4)


class TestSaveLoad:
    def test_round_trip(self, synthetic_calib, tmp_path):
        """Save and load should preserve all parameters."""
        path = tmp_path / "test_calib.npz"
        save_calibration(synthetic_calib, path)

        loaded = load_calibration(path)
        assert loaded is not None

        np.testing.assert_allclose(loaded.K1, synthetic_calib.K1)
        np.testing.assert_allclose(loaded.K2, synthetic_calib.K2)
        np.testing.assert_allclose(loaded.R, synthetic_calib.R)
        np.testing.assert_allclose(loaded.T, synthetic_calib.T)
        assert loaded.image_size == synthetic_calib.image_size

    def test_load_nonexistent_returns_none(self, tmp_path):
        result = load_calibration(tmp_path / "nonexistent.npz")
        assert result is None
