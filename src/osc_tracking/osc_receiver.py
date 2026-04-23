"""OSC receiver for IMU tracker data.

Receives rotation quaternion data from any OSC-compatible IMU tracker.
Tested with HaritoraX2 via SlimeTora → SlimeVR Server; other
SlimeVR-Server-compatible trackers (SlimeVR native, Tundra, etc.) use
the same address pattern and should work without code changes.

Architecture:
    IMU tracker ──UDP/OSC──► OSCReceiver ──► FusionEngine
                                │
                           Parses quaternion
                           per bone, tracks
                           last-received time
"""

import logging
import math
import time

from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer
from scipy.spatial.transform import Rotation

from .receiver_base import BaseIMUReceiver, BoneData
from .tracker_mapping import slimevr_osc_addresses

logger = logging.getLogger(__name__)

# Re-exported so existing callers that do `from .osc_receiver import BoneData`
# keep working; the canonical definition lives in receiver_base.
__all__ = ["BoneData", "OSCReceiver"]


class OSCReceiver(BaseIMUReceiver):
    """Receives and parses IMU tracker OSC messages.

    Expects SlimeVR Server OSC output format (see DEFAULT_BONE_ADDRESSES).
    Works with any tracker that routes through SlimeVR Server, including
    HaritoraX2 via SlimeTora, SlimeVR native trackers, and Tundra Labs.
    """

    # SlimeVR Server OSC output mapping (tracker indices 1-8).
    # HaritoraX2 reaches this path via SlimeTora → SlimeVR Server.
    # SlimeVR native / Tundra reach it directly from SlimeVR Server.
    #
    # NOTE: IMU trackers here send rotation ONLY (no position).
    # Mapping table is derived from the shared tracker_mapping module so
    # that BLE and OSC receivers stay on the same 8-tracker roster.
    DEFAULT_BONE_ADDRESSES = slimevr_osc_addresses()

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 6969,
        bone_addresses: dict[str, str] | None = None,
    ):
        super().__init__()
        self.host = host
        self.port = port
        self.bone_addresses = bone_addresses or self.DEFAULT_BONE_ADDRESSES
        self.bones = {name: BoneData() for name in self.bone_addresses.values()}
        self._server: BlockingOSCUDPServer | None = None

    def _thread_name(self) -> str:
        return "osc-receiver"

    def _prepare_start(self) -> None:
        """Bind the OSC server (with port-retry fallback) before thread spawn.

        Retry logic runs here so an unrecoverable bind error surfaces as
        an OSError from ``start()`` with the receiver left in a clean
        stopped state, matching the pre-refactor behavior.
        """
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
                original_port = self.port
                for attempt in range(1, 4):
                    try:
                        self.port = original_port + attempt
                        self._server = BlockingOSCUDPServer(
                            (self.host, self.port), dispatcher
                        )
                        break
                    except OSError:
                        if attempt == 3:
                            raise
                logger.warning(
                    "Port %d in use, using %d instead. "
                    "Make sure SlimeVR Server sends to port %d.",
                    original_port, self.port, self.port,
                )
            else:
                raise

    def _run_loop(self) -> None:
        assert self._server is not None
        self._server.serve_forever()

    def _on_stop_requested(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server = None

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
            # Normalize quaternion to unit length
            norm = math.sqrt(x * x + y * y + z * z + w * w)
            if norm < 1e-6:
                return
            quat = [x / norm, y / norm, z / norm, w / norm]
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
