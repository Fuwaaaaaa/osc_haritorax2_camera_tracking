"""VisionProvider Protocol conformance tests.

Any class acting as the skeleton's optical sensor (MediaPipe dual-cam,
OpenPose, a playback file, a mock) must conform to this Protocol.
"""

from __future__ import annotations

import numpy as np

from osc_tracking.camera_protocol import VisionProvider
from osc_tracking.camera_tracker import CameraTracker


def test_camera_tracker_conforms_to_vision_provider():
    tracker = CameraTracker()
    assert isinstance(tracker, VisionProvider)


def test_vision_provider_protocol_is_runtime_checkable():
    """Duck-typed adapters should pass isinstance checks."""

    class FakeProvider:
        @property
        def is_alive(self) -> bool:
            return True

        def start(self) -> None:
            pass

        def stop(self) -> None:
            pass

        def read_joints(self):
            return None

    assert isinstance(FakeProvider(), VisionProvider)


def test_non_conforming_object_fails_protocol_check():
    class Incomplete:
        def start(self) -> None:
            pass

    assert not isinstance(Incomplete(), VisionProvider)


def test_fake_provider_can_feed_fusion_engine(monkeypatch):
    """Proves the Protocol is sufficient — FusionEngine works with any
    conforming object, not just the concrete CameraTracker."""
    from unittest.mock import MagicMock

    from scipy.spatial.transform import Rotation

    from osc_tracking.complementary_filter import JOINT_NAMES
    from osc_tracking.fusion_engine import FusionEngine

    class FakeCamera:
        is_alive = True

        def start(self):
            pass

        def stop(self):
            pass

        def read_joints(self):
            return {
                name: (np.array([0.0, 1.0, 2.0]), 0.9, 0.9, 0.9)
                for name in JOINT_NAMES
            }

    fake = FakeCamera()
    assert isinstance(fake, VisionProvider)
    recv = MagicMock()
    recv.is_connected = True
    recv.get_bone_rotation.return_value = Rotation.identity()
    sender = MagicMock()
    engine = FusionEngine(camera=fake, receiver=recv, sender=sender)
    mode = engine.update()
    assert mode is not None
