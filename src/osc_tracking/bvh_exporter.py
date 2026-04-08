"""BVH motion capture file exporter.

Exports tracking data to BVH format for playback in Blender,
MotionBuilder, Unity, etc.
"""

import logging
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

logger = logging.getLogger(__name__)

# Simplified skeleton hierarchy for BVH
BVH_HIERARCHY = {
    "Hips": {"parent": None, "offset": (0, 100, 0)},
    "Chest": {"parent": "Hips", "offset": (0, 30, 0)},
    "Head": {"parent": "Chest", "offset": (0, 30, 0)},
    "LeftElbow": {"parent": "Chest", "offset": (-20, 0, 0)},
    "RightElbow": {"parent": "Chest", "offset": (20, 0, 0)},
    "LeftKnee": {"parent": "Hips", "offset": (-10, -45, 0)},
    "RightKnee": {"parent": "Hips", "offset": (10, -45, 0)},
    "LeftFoot": {"parent": "LeftKnee", "offset": (0, -45, 0)},
    "RightFoot": {"parent": "RightKnee", "offset": (0, -45, 0)},
}


class BVHExporter:
    """Accumulates frames and exports to BVH file."""

    def __init__(self, fps: float = 30.0):
        self.fps = fps
        self._frames: list[dict[str, tuple[np.ndarray, Rotation]]] = []

    def add_frame(self, joints: dict[str, tuple[np.ndarray, Rotation]]) -> None:
        self._frames.append(joints)

    def export(self, filepath: str | Path) -> int:
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)

        joint_order = list(BVH_HIERARCHY.keys())

        with open(filepath, "w") as f:
            # Write hierarchy
            f.write("HIERARCHY\n")
            self._write_joint(f, "Hips", 0, joint_order)

            # Write motion data
            f.write("MOTION\n")
            f.write(f"Frames: {len(self._frames)}\n")
            f.write(f"Frame Time: {1.0 / self.fps:.6f}\n")

            for frame in self._frames:
                values = []
                for name in joint_order:
                    if name in frame:
                        pos, rot = frame[name]
                        euler = rot.as_euler("ZXY", degrees=True)
                    else:
                        pos = np.zeros(3)
                        euler = np.zeros(3)

                    if name == "Hips":
                        # Root joint has position + rotation
                        values.extend([float(pos[0] * 100), float(pos[1] * 100), float(pos[2] * 100)])
                    values.extend([float(euler[2]), float(euler[0]), float(euler[1])])

                f.write(" ".join(f"{v:.4f}" for v in values) + "\n")

        logger.info("Exported %d frames to %s", len(self._frames), filepath)
        return len(self._frames)

    def _write_joint(self, f, name: str, depth: int, order: list[str]) -> None:
        indent = "  " * depth
        info = BVH_HIERARCHY[name]
        children = [n for n, v in BVH_HIERARCHY.items() if v["parent"] == name]

        tag = "ROOT" if info["parent"] is None else "JOINT"
        f.write(f"{indent}{tag} {name}\n")
        f.write(f"{indent}{{\n")

        ox, oy, oz = info["offset"]
        f.write(f"{indent}  OFFSET {ox:.4f} {oy:.4f} {oz:.4f}\n")

        if info["parent"] is None:
            f.write(f"{indent}  CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation\n")
        else:
            f.write(f"{indent}  CHANNELS 3 Zrotation Xrotation Yrotation\n")

        if children:
            for child in children:
                self._write_joint(f, child, depth + 1, order)
        else:
            f.write(f"{indent}  End Site\n")
            f.write(f"{indent}  {{\n")
            f.write(f"{indent}    OFFSET 0.0000 0.0000 0.0000\n")
            f.write(f"{indent}  }}\n")

        f.write(f"{indent}}}\n")

    def clear(self) -> None:
        self._frames.clear()

    @property
    def frame_count(self) -> int:
        return len(self._frames)
