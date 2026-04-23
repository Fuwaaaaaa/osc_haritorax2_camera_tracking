"""Persistence-layer Protocols — the boundary between domain and storage.

Repository Protocols define *what* persistence operations are needed
(load calibration, write a recording, save a config). Concrete adapters
live in sibling modules and implement these with actual file / JSON / npz I/O.

Callers in the application layer should type their dependencies against
these Protocols rather than the concrete adapters, so the underlying
storage can be swapped (e.g. file → S3 → SQLite) without touching
business logic.
"""

from osc_tracking.persistence.protocols import (
    CalibrationRepository,
    ConfigRepository,
    RecordingRepository,
)

__all__ = [
    "CalibrationRepository",
    "ConfigRepository",
    "RecordingRepository",
]
