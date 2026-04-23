"""Repository Protocols — the storage boundary for the application layer.

Each Protocol describes the minimum operations an adapter must offer.
``@runtime_checkable`` so tests can assert conformance of concrete
adapters without manually mirroring the types.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class CalibrationRepository(Protocol):
    """Stereo calibration storage.

    ``load()`` returns an implementation-specific object (today: a
    ``StereoCalibration`` dataclass); callers treat it as opaque.
    Returns ``None`` when no calibration exists yet.
    """

    def load(self) -> Any | None: ...


@runtime_checkable
class RecordingRepository(Protocol):
    """Tracking session recorder.

    The ``record_frame`` signature mirrors the current recorder contract
    and will tighten once callers migrate to SkeletonSnapshot-based data.
    """

    def start(self, filename: str | None = ...) -> Path: ...

    def record_frame(self, joints_data: dict, mode: str) -> None: ...

    def stop(self) -> int: ...


@runtime_checkable
class ConfigRepository(Protocol):
    """Tracking configuration storage.

    Today's adapter is :meth:`TrackingConfig.load` / :meth:`save`;
    promoting these to a Protocol lets tests inject in-memory configs.
    """

    def save(self, path: Path | None = ...) -> None: ...
