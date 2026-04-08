"""OSC sender for VRChat and VMC Protocol output.

Sends fused tracking data to VRChat via OSC protocol.
Supports both VRChat native OSC and VMC Protocol.

Architecture:
    FusionEngine ──► OSCSender ──UDP/OSC──► VRChat
"""

import logging
import time
from dataclasses import dataclass

import numpy as np
from pythonosc.udp_client import SimpleUDPClient
from scipy.spatial.transform import Rotation

logger = logging.getLogger(__name__)


@dataclass
class TrackerOutput:
    """Fused tracking data for one joint, ready to send."""
    position: np.ndarray  # (x, y, z)
    rotation: Rotation
    joint_name: str


class OSCSender:
    """Sends fused tracking data to VRChat via OSC.

    VRChat OSC tracker format:
        /tracking/trackers/{id}/position  x y z
        /tracking/trackers/{id}/rotation  x y z  (euler degrees)
    """

    # VRChat OSC tracker ID mapping
    # VRChat supports up to 8 OSC trackers
    JOINT_TO_TRACKER_ID = {
        "Hips": 1,
        "Chest": 2,
        "Head": 3,
        "LeftFoot": 4,
        "RightFoot": 5,
        "LeftKnee": 6,
        "RightKnee": 7,
        "LeftElbow": 8,
        # RightElbow omitted — VRChat 8-tracker limit
    }

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9000,
        retry_interval: float = 5.0,
    ):
        self.host = host
        self.port = port
        self.retry_interval = retry_interval
        self._client: SimpleUDPClient | None = None
        self._last_retry: float = 0.0
        self._connected = False

    def connect(self) -> bool:
        """Create the UDP client. Returns True on success."""
        try:
            self._client = SimpleUDPClient(self.host, self.port)
            self._connected = True
            return True
        except OSError as e:
            logger.warning("VRChat OSC connection failed: %s", e)
            self._connected = False
            return False

    def send(self, outputs: list[TrackerOutput]) -> bool:
        """Send a batch of tracker outputs.

        Returns True if all messages were sent, False on failure.
        """
        if not self._connected:
            now = time.monotonic()
            if now - self._last_retry < self.retry_interval:
                return False
            self._last_retry = now
            if not self.connect():
                return False

        try:
            client = self._client
            if client is None:
                return False

            for output in outputs:
                tracker_id = self.JOINT_TO_TRACKER_ID.get(output.joint_name)
                if tracker_id is None:
                    continue

                pos = output.position
                euler = output.rotation.as_euler("xyz", degrees=True)

                client.send_message(
                    f"/tracking/trackers/{tracker_id}/position",
                    [float(pos[0]), float(pos[1]), float(pos[2])],
                )
                client.send_message(
                    f"/tracking/trackers/{tracker_id}/rotation",
                    [float(euler[0]), float(euler[1]), float(euler[2])],
                )
            return True
        except OSError as e:
            logger.warning("OSC send failed: %s. Will retry.", e)
            self._connected = False
            return False

    def close(self) -> None:
        """Clean up the client."""
        self._client = None
        self._connected = False
