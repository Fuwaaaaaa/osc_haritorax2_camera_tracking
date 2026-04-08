"""CSV/JSON data exporter — export tracking data for analysis.

Exports tracking session data to CSV or JSON for use in
spreadsheets, Jupyter notebooks, or data analysis tools.
"""

import csv
import json
import logging
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from .complementary_filter import JOINT_NAMES

logger = logging.getLogger(__name__)


class DataExporter:
    """Accumulates frames and exports to CSV or JSON."""

    def __init__(self):
        self._frames: list[dict] = []

    def add_frame(
        self,
        timestamp: float,
        mode: str,
        fps: float,
        joints: dict[str, tuple[np.ndarray, Rotation, float]],
    ) -> None:
        row = {"timestamp": round(timestamp, 4), "mode": mode, "fps": round(fps, 1)}
        for name in JOINT_NAMES:
            if name in joints:
                pos, rot, conf = joints[name]
                euler = rot.as_euler("xyz", degrees=True)
                row[f"{name}_x"] = round(float(pos[0]), 5)
                row[f"{name}_y"] = round(float(pos[1]), 5)
                row[f"{name}_z"] = round(float(pos[2]), 5)
                row[f"{name}_rx"] = round(float(euler[0]), 2)
                row[f"{name}_ry"] = round(float(euler[1]), 2)
                row[f"{name}_rz"] = round(float(euler[2]), 2)
                row[f"{name}_conf"] = round(float(conf), 3)
        self._frames.append(row)

    def export_csv(self, filepath: str | Path) -> int:
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)

        if not self._frames:
            return 0

        fieldnames = list(self._frames[0].keys())
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self._frames)

        logger.info("Exported %d frames to %s", len(self._frames), filepath)
        return len(self._frames)

    def export_json(self, filepath: str | Path) -> int:
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self._frames, f, indent=2, ensure_ascii=False)

        logger.info("Exported %d frames to %s", len(self._frames), filepath)
        return len(self._frames)

    def clear(self) -> None:
        self._frames.clear()

    @property
    def frame_count(self) -> int:
        return len(self._frames)
