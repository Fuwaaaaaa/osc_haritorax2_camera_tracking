"""Structural protocol for optical skeleton providers.

Any component that feeds 3D joint positions to :class:`FusionEngine`
must satisfy this Protocol: the current :class:`CameraTracker`
(dual-cam MediaPipe + triangulation), a hypothetical OpenPose adapter,
a playback-file provider for offline testing, or a test fake.

The :func:`runtime_checkable` decorator lets callers write
``isinstance(provider, VisionProvider)`` in verification scripts.

Contract
--------
- ``is_alive`` is ``True`` while the backing subprocess / pipeline is
  running. It does not imply fresh data.
- ``read_joints()`` returns the latest per-joint data or ``None`` when
  the provider has no data (never attached, process crashed, etc).
  The returned dict maps ``joint_name`` to the 4-tuple
  ``(position_xyz, combined_confidence, cam1_confidence, cam2_confidence)``.
  Providers that have fewer than two cameras may report the same value
  for ``cam1`` and ``cam2``.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class VisionProvider(Protocol):
    """Pull-style interface exposed by every optical skeleton provider."""

    @property
    def is_alive(self) -> bool: ...

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def read_joints(
        self,
    ) -> dict[str, tuple[np.ndarray, float, float, float]] | None: ...
