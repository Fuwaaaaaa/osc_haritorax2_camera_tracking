"""VMC Protocol sender for VirtualMotionCapture-compatible applications.

Sends tracking data using the VMC Protocol (Virtual Motion Capture Protocol)
for compatibility with apps like VirtualMotionCapture, Resonite, ChilloutVR,
VDRAW, Warudo, etc.

VMC Protocol reference: https://protocol.vmc.info/
"""

import logging

import numpy as np
from pythonosc.udp_client import SimpleUDPClient
from scipy.spatial.transform import Rotation

logger = logging.getLogger(__name__)

# VMC bone name mapping (Unity HumanBodyBones)
JOINT_TO_VMC_BONE = {
    "Hips": "Hips",
    "Chest": "Spine",
    "Head": "Head",
    "LeftElbow": "LeftLowerArm",
    "RightElbow": "RightLowerArm",
    "LeftKnee": "LeftLowerLeg",
    "RightKnee": "RightLowerLeg",
    "LeftFoot": "LeftFoot",
    "RightFoot": "RightFoot",
}


class VMCSender:
    """Sends tracking data using VMC Protocol over OSC."""

    def __init__(self, host: str = "127.0.0.1", port: int = 39539):
        self.host = host
        self.port = port
        self._client: SimpleUDPClient | None = None

    def connect(self) -> bool:
        try:
            self._client = SimpleUDPClient(self.host, self.port)
            return True
        except OSError as e:
            logger.warning("VMC connection failed: %s", e)
            return False

    def send_frame(self, joints: dict[str, tuple[np.ndarray, Rotation]]) -> None:
        if self._client is None:
            return

        try:
            # Send root transform (Hips)
            if "Hips" in joints:
                pos, rot = joints["Hips"]
                quat = rot.as_quat()  # x, y, z, w
                self._client.send_message(
                    "/VMC/Ext/Root/Pos",
                    ["Root", float(pos[0]), float(pos[1]), float(pos[2]),
                     float(quat[0]), float(quat[1]), float(quat[2]), float(quat[3])],
                )

            # Send bone rotations
            for joint_name, (pos, rot) in joints.items():
                vmc_bone = JOINT_TO_VMC_BONE.get(joint_name)
                if vmc_bone is None:
                    continue

                quat = rot.as_quat()
                self._client.send_message(
                    "/VMC/Ext/Bone/Pos",
                    [vmc_bone, float(pos[0]), float(pos[1]), float(pos[2]),
                     float(quat[0]), float(quat[1]), float(quat[2]), float(quat[3])],
                )

            # Send availability signal
            self._client.send_message("/VMC/Ext/OK", [1])

        except OSError:
            logger.warning("VMC send failed")

    def close(self) -> None:
        self._client = None
