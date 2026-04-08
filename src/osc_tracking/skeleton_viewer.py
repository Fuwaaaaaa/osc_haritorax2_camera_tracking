"""3D skeleton viewer using matplotlib.

Displays real-time 3D skeleton with joint connections.
"""

import logging

import numpy as np

logger = logging.getLogger(__name__)

BONE_CONNECTIONS = [
    ("Hips", "Chest"), ("Chest", "Head"),
    ("Chest", "LeftElbow"), ("Chest", "RightElbow"),
    ("Hips", "LeftKnee"), ("Hips", "RightKnee"),
    ("LeftKnee", "LeftFoot"), ("RightKnee", "RightFoot"),
]


class SkeletonViewer:
    """Real-time 3D skeleton visualization."""

    def __init__(self):
        self._fig = None
        self._ax = None
        self._initialized = False

    def start(self) -> None:
        try:
            import matplotlib
            matplotlib.use("TkAgg")
            import matplotlib.pyplot as plt
            from mpl_toolkits.mplot3d import Axes3D  # noqa: F401

            plt.ion()
            self._fig = plt.figure(figsize=(8, 8))
            self._ax = self._fig.add_subplot(111, projection="3d")
            self._ax.set_xlim(-1, 1)
            self._ax.set_ylim(0, 2)
            self._ax.set_zlim(-1, 1)
            self._ax.set_xlabel("X")
            self._ax.set_ylabel("Y")
            self._ax.set_zlabel("Z")
            self._ax.set_title("OSC Tracking — Skeleton View")
            self._initialized = True
            logger.info("Skeleton viewer started")
        except Exception as e:
            logger.warning("Skeleton viewer unavailable: %s", e)

    def update(self, joints: dict[str, np.ndarray]) -> None:
        if not self._initialized:
            return


        self._ax.cla()
        self._ax.set_xlim(-1, 1)
        self._ax.set_ylim(0, 2)
        self._ax.set_zlim(-1, 1)
        self._ax.set_xlabel("X")
        self._ax.set_ylabel("Y")
        self._ax.set_zlabel("Z")

        # Draw joints
        for name, pos in joints.items():
            self._ax.scatter(*pos, c="cyan", s=50, depthshade=True)
            self._ax.text(pos[0], pos[1], pos[2], f" {name}", fontsize=6, color="white")

        # Draw bones
        for a, b in BONE_CONNECTIONS:
            if a in joints and b in joints:
                pa, pb = joints[a], joints[b]
                self._ax.plot([pa[0], pb[0]], [pa[1], pb[1]], [pa[2], pb[2]], c="lime", linewidth=2)

        self._fig.canvas.draw_idle()
        self._fig.canvas.flush_events()

    def stop(self) -> None:
        if self._initialized:
            import matplotlib.pyplot as plt
            plt.close(self._fig)
            self._initialized = False
