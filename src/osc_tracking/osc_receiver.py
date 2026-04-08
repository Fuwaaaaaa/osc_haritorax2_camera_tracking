"""OSC receiver for HaritoraX2 tracker data.

Receives rotation quaternion data from HaritoraX2 via OSC protocol.
The actual OSC address patterns and data format should be documented
in docs/haritora-osc-format.md after Phase 0 investigation.

Architecture:
    HaritoraX2 ──UDP/OSC──► OSCReceiver ──► FusionEngine
                              │
                         Parses quaternion
                         per bone, tracks
                         last-received time
"""

import math
import threading
import time
from dataclasses import dataclass, field

from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer
from scipy.spatial.transform import Rotation


@dataclass
class BoneData:
    """Rotation data for a single bone."""
    rotation: Rotation = field(default_factory=Rotation.identity)
    timestamp: float = 0.0


class OSCReceiver:
    """Receives and parses HaritoraX2 OSC messages.

    NOTE: The default OSC address patterns below are placeholders.
    Phase 0 will capture actual HaritoraX2 messages and update these.
    """

    # HaritoraX2 tracker mapping.
    # HaritoraX2 communicates via BLE/Serial, NOT OSC directly.
    # Use SlimeTora → SlimeVR Server → OSC output as the bridge.
    # SlimeVR Server OSC output uses tracker indices.
    #
    # HaritoraX2 native tracker names:
    #   chest, hip, rightElbow, leftElbow,
    #   rightKnee, rightAnkle, leftKnee, leftAnkle
    #
    # NOTE: HaritoraX2 sends rotation ONLY (no position).
    DEFAULT_BONE_ADDRESSES = {
        "/tracking/trackers/1/rotation": "Hips",       # hip tracker
        "/tracking/trackers/2/rotation": "Chest",       # chest tracker
        "/tracking/trackers/3/rotation": "LeftFoot",    # leftAnkle tracker
        "/tracking/trackers/4/rotation": "RightFoot",   # rightAnkle tracker
        "/tracking/trackers/5/rotation": "LeftKnee",    # leftKnee tracker
        "/tracking/trackers/6/rotation": "RightKnee",   # rightKnee tracker
        "/tracking/trackers/7/rotation": "LeftElbow",   # leftElbow tracker
        "/tracking/trackers/8/rotation": "RightElbow",  # rightElbow tracker
    }

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 6969,
        bone_addresses: dict[str, str] | None = None,
    ):
        self.host = host
        self.port = port
        self.bone_addresses = bone_addresses or self.DEFAULT_BONE_ADDRESSES
        self.bones: dict[str, BoneData] = {
            name: BoneData() for name in self.bone_addresses.values()
        }
        self._server: BlockingOSCUDPServer | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._last_receive_time: float = 0.0

    @property
    def is_connected(self) -> bool:
        """True if OSC data was received within the last second."""
        return (time.monotonic() - self._last_receive_time) < 1.0

    @property
    def seconds_since_last_receive(self) -> float:
        if self._last_receive_time == 0.0:
            return float("inf")
        return time.monotonic() - self._last_receive_time

    def start(self) -> None:
        """Start the OSC server in a background thread."""
        if self._running:
            return

        dispatcher = Dispatcher()
        for address, bone_name in self.bone_addresses.items():
            dispatcher.map(address, self._handle_rotation, bone_name)
        dispatcher.set_default_handler(self._handle_unknown)

        try:
            self._server = BlockingOSCUDPServer(
                (self.host, self.port), dispatcher
            )
        except OSError as e:
            if e.errno == 10048 or "Address already in use" in str(e):
                # Try alternative port
                self._server = BlockingOSCUDPServer(
                    (self.host, self.port + 1), dispatcher
                )
                self.port += 1
            else:
                raise

        self._running = True
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
            name="osc-receiver",
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop the OSC server."""
        self._running = False
        if self._server:
            self._server.shutdown()
            self._server = None
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def get_bone_rotation(self, bone_name: str) -> Rotation | None:
        """Get the latest rotation for a bone, or None if stale."""
        bone = self.bones.get(bone_name)
        if bone is None:
            return None
        if time.monotonic() - bone.timestamp > 1.0:
            return None
        return bone.rotation

    def _handle_rotation(
        self, address: str, bone_name: str, *args: float
    ) -> None:
        """Handle incoming rotation quaternion (x, y, z, w)."""
        if len(args) < 4:
            return
        try:
            x, y, z, w = float(args[0]), float(args[1]), float(args[2]), float(args[3])
            quat = [x, y, z, w]
            if not all(math.isfinite(v) for v in quat):
                return
            self.bones[bone_name] = BoneData(
                rotation=Rotation.from_quat(quat),
                timestamp=time.monotonic(),
            )
            self._last_receive_time = time.monotonic()
        except (ValueError, TypeError):
            pass

    def _handle_unknown(self, address: str, *args) -> None:
        """Log unknown OSC addresses for Phase 0 investigation."""
        pass  # Could log to file for format discovery


