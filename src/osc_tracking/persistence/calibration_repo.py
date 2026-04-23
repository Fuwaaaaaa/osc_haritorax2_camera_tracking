"""File-backed stereo calibration repository.

Thin adapter over :func:`stereo_calibration.load_calibration` that
satisfies the :class:`CalibrationRepository` Protocol. The adapter
exists so the application layer can depend on the Protocol while
tests inject in-memory or file-missing variants.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from osc_tracking.stereo_calibration import StereoCalibration


class FileCalibrationRepository:
    """Loads a stored :class:`StereoCalibration` from a ``.npz`` path.

    The path is normalised at construction time so a malicious config
    value like ``../../etc/passwd`` cannot reach unrelated files: the
    resolved path must lie within the process's current working
    directory tree (i.e. alongside ``calibration_data/`` by default).
    """

    def __init__(self, path: str | Path) -> None:
        raw = Path(path)
        try:
            resolved = raw.resolve()
            cwd = Path.cwd().resolve()
            resolved.relative_to(cwd)
        except (ValueError, OSError):
            logger.warning(
                "Calibration path %s escapes the project tree; "
                "refusing to load.", raw,
            )
            # Store an obviously-missing path so load() returns None.
            resolved = cwd / "_rejected_calibration_path.npz"
        self._path = resolved

    def load(self) -> StereoCalibration | None:
        # Lazy import so that test contexts not using calibration don't
        # pay the cv2 / numpy import cost through this module.
        from osc_tracking.stereo_calibration import load_calibration
        return load_calibration(self._path)
