"""Data recording and playback for sensor data.

Records all tracking data (camera positions, IMU rotations, confidence,
timestamps) to a JSON Lines file. Can replay the data to reproduce
exact tracking sessions for debugging and parameter tuning.
"""

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from scipy.spatial.transform import Rotation

logger = logging.getLogger(__name__)


@dataclass
class RecordedFrame:
    """Single frame of recorded tracking data."""
    timestamp: float
    joints: dict  # joint_name -> {position: [x,y,z], rotation: [x,y,z,w], confidence: float}
    mode: str


class TrackingRecorder:
    """Records tracking data to a JSONL file."""

    def __init__(self, output_dir: str = "recordings"):
        self.output_dir = Path(output_dir)
        from typing import IO
        self._file: IO[str] | None = None
        self._start_time = 0.0
        self._frame_count = 0

    def start(self, filename: str | None = None) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        if filename is None:
            filename = f"recording_{time.strftime('%Y%m%d_%H%M%S')}.jsonl"
        self._path = self.output_dir / filename
        self._file = open(self._path, "w", encoding="utf-8")
        self._start_time = time.monotonic()
        self._frame_count = 0
        logger.info("Recording started: %s", self._path)
        return self._path

    def record_frame(self, joints_data: dict, mode: str) -> None:
        if self._file is None:
            return

        from typing import Any
        frame: dict[str, Any] = {
            "t": round(time.monotonic() - self._start_time, 4),
            "mode": mode,
            "joints": {},
        }

        for name, (pos, rot, conf) in joints_data.items():
            quat = rot.as_quat().tolist() if isinstance(rot, Rotation) else [0, 0, 0, 1]
            frame["joints"][name] = {
                "p": [round(float(v), 5) for v in pos],
                "r": [round(float(v), 5) for v in quat],
                "c": round(float(conf), 3),
            }

        self._file.write(json.dumps(frame, ensure_ascii=False) + "\n")
        self._frame_count += 1

    def stop(self) -> int:
        if self._file:
            self._file.close()
            self._file = None
            logger.info("Recording stopped: %d frames saved to %s", self._frame_count, self._path)
        return self._frame_count


class TrackingPlayer:
    """Replays recorded tracking data from a JSONL file."""

    def __init__(self, filepath: str | Path):
        self._path = Path(filepath)
        self._frames: list[dict] = []
        self._index = 0

    def load(self) -> int:
        self._frames = []
        with open(self._path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    self._frames.append(json.loads(line))
        self._index = 0
        logger.info("Loaded %d frames from %s", len(self._frames), self._path)
        return len(self._frames)

    def next_frame(self) -> dict | None:
        if self._index >= len(self._frames):
            return None
        frame = self._frames[self._index]
        self._index += 1
        return frame

    def reset(self) -> None:
        self._index = 0

    @property
    def total_frames(self) -> int:
        return len(self._frames)

    @property
    def current_index(self) -> int:
        return self._index

    @property
    def is_done(self) -> bool:
        return self._index >= len(self._frames)
