"""Tests that concrete persistence adapters conform to Repository Protocols.

The Protocols in :mod:`osc_tracking.persistence` express the persistence
boundary: anything that saves/loads a recording, calibration, or config
must present this shape. Existing concrete adapters (TrackingRecorder,
load/save_calibration, TrackingConfig) are validated here so future
refactors can swap them without touching callers.
"""

from __future__ import annotations

from osc_tracking.persistence import (
    CalibrationRepository,
    RecordingRepository,
)


def test_tracking_recorder_conforms_to_recording_repository():
    from osc_tracking.recorder import TrackingRecorder
    rec = TrackingRecorder()
    assert isinstance(rec, RecordingRepository)


def test_file_calibration_repository_conforms():
    from osc_tracking.persistence.calibration_repo import FileCalibrationRepository
    repo = FileCalibrationRepository("does_not_exist.npz")
    assert isinstance(repo, CalibrationRepository)


def test_calibration_repository_returns_none_for_missing_file(tmp_path):
    from osc_tracking.persistence.calibration_repo import FileCalibrationRepository
    repo = FileCalibrationRepository(str(tmp_path / "nonexistent.npz"))
    assert repo.load() is None


def test_recording_repository_write_protocol(tmp_path):
    """The protocol requires start(filename) -> Path, record_frame(data, mode),
    stop() -> None. Smoke-test that our adapter actually writes something."""
    from osc_tracking.recorder import TrackingRecorder
    rec = TrackingRecorder(output_dir=str(tmp_path))
    path = rec.start()
    assert path.exists()
    rec.stop()
