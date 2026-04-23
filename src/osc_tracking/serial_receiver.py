"""Direct serial (COM/SPP) receiver for HaritoraX-family IMU trackers.

EXPERIMENTAL. Bypasses SlimeTora + SlimeVR Server by reading straight
from a GX6/GX2 USB dongle or a Bluetooth Classic (SPP) COM port.
Requires hardware for real validation.

Protocol reference (adapted from haritorax-interpreter, MIT licensed):
    https://github.com/JovannMC/haritorax-interpreter
    src/mode/com.ts (serial read/write loop)
    src/HaritoraX.ts::decodeIMUPacket (rotation layout — shared with BLE)

Wire format
-----------
Frames are fixed-length binary packets delimited by a 2-byte sync
prefix so the reader can resync after garbage on the line::

    [0xAA][0x55]       sync pattern (2 bytes)
    [tracker_id]       u8  (0..7 on GX6, 0..1 on GX2)
    [rotationX]        int16 LE, * 0.01/180.0
    [rotationY]        int16 LE, * 0.01/180.0
    [rotationZ]        int16 LE, * -0.01/180.0  (sign flipped)
    [rotationW]        int16 LE, * -0.01/180.0  (sign flipped)

Total: 11 bytes per frame.

The quaternion decoder is shared with :mod:`ble_receiver` because
HaritoraX dongles re-emit the BLE sensor payload verbatim.

Threading
---------
A dedicated daemon thread owns the serial port. It accumulates bytes,
hands them to :func:`parse_frames`, and dispatches each decoded frame
to :meth:`_handle_frame`. Reads on the main thread go through
``get_bone_rotation`` (inherited from BaseIMUReceiver), guarded by a
1-second freshness window — the same contract as ``OSCReceiver`` and
``BLEReceiver``.
"""

from __future__ import annotations

import logging
import time

from scipy.spatial.transform import Rotation

from .ble_receiver import decode_rotation
from .receiver_base import BaseIMUReceiver, BoneData

logger = logging.getLogger(__name__)

# Frame layout
SYNC_BYTES = b"\xaa\x55"
FRAME_LENGTH = len(SYNC_BYTES) + 1 + 8  # sync + tracker_id + 4x int16

# Seconds to wait for a fresh sample before is_connected flips to False.
FRESHNESS_WINDOW_SEC = 1.0

# Seconds to back off between open retries when the port is unavailable.
RECONNECT_DELAY_SEC = 2.0

# Maximum unparsed byte buffer retained between reads. A misbehaving or
# hostile COM device that streams garbage without the sync pattern would
# otherwise grow the buffer without bound, eventually OOM-killing the
# process. ~4 frames worth is plenty for resync at 500 kbps.
MAX_BUFFER_BYTES = 4096

# GX6/GX2 dongle default baud rate per haritorax-interpreter.
DEFAULT_BAUDRATE = 500000

# Re-exported so existing callers keep working after the base-class migration.
__all__ = [
    "BoneData",
    "DEFAULT_BAUDRATE",
    "FRESHNESS_WINDOW_SEC",
    "FRAME_LENGTH",
    "MAX_BUFFER_BYTES",
    "RECONNECT_DELAY_SEC",
    "SYNC_BYTES",
    "SerialReceiver",
    "parse_frames",
]


def parse_frames(buffer: bytes) -> tuple[list[tuple[int, bytes]], bytes]:
    """Extract complete frames from ``buffer``.

    Returns ``(frames, remainder)`` where:
    - ``frames`` is a list of ``(tracker_id, payload)`` tuples; ``payload``
      is the 8-byte quaternion slice (no sync or id bytes).
    - ``remainder`` is the unconsumed tail, starting at a sync-byte prefix
      when possible so the next read can complete a partial frame.

    Any bytes before the first sync pattern are discarded as garbage.
    The parser is strictly length-framed: a sync pattern appearing
    inside a quaternion payload cannot resync the stream mid-frame.
    """
    frames: list[tuple[int, bytes]] = []
    buf = buffer
    while True:
        idx = buf.find(SYNC_BYTES)
        if idx < 0:
            # No sync found anywhere — keep at most the last byte in case
            # it's the first half of a sync pattern.
            if buf and buf[-1:] == SYNC_BYTES[:1]:
                return frames, buf[-1:]
            return frames, b""
        if idx > 0:
            buf = buf[idx:]
        if len(buf) < FRAME_LENGTH:
            return frames, buf
        tracker_id = buf[len(SYNC_BYTES)]
        payload = bytes(buf[len(SYNC_BYTES) + 1 : FRAME_LENGTH])
        frames.append((tracker_id, payload))
        buf = buf[FRAME_LENGTH:]


def _open_serial(port: str, baudrate: int):
    """Open a pyserial port. Isolated for test-time patching."""
    import serial  # type: ignore[import-not-found]

    return serial.Serial(port=port, baudrate=baudrate, timeout=0.1)


class SerialReceiver(BaseIMUReceiver):
    """Receives IMU rotation data from a HaritoraX dongle over a COM port.

    Parameters
    ----------
    port
        Serial port name (e.g. ``"COM3"`` on Windows, ``"/dev/ttyUSB0"`` on Linux).
    tracker_id_to_bone
        Maps the per-dongle tracker id (0..7) to the skeleton bone name.
    baudrate
        Line rate; ``500000`` matches the HaritoraX GX6 default.
    reconnect_delay_sec
        Back-off between failed open attempts.
    """

    def __init__(
        self,
        port: str,
        tracker_id_to_bone: dict[int, str] | None = None,
        baudrate: int = DEFAULT_BAUDRATE,
        reconnect_delay_sec: float = RECONNECT_DELAY_SEC,
    ) -> None:
        super().__init__(freshness_window_sec=FRESHNESS_WINDOW_SEC)
        mapping = dict(tracker_id_to_bone or {})
        self._warn_on_unknown_bones(mapping)
        self.port = port
        self.baudrate = int(baudrate)
        self.tracker_id_to_bone: dict[int, str] = mapping
        self.reconnect_delay_sec = float(reconnect_delay_sec)

        self.bones = {
            bone: BoneData() for bone in self.tracker_id_to_bone.values()
        }
        self._serial = None

    @staticmethod
    def _warn_on_unknown_bones(mapping: dict[int, str]) -> None:
        """Warn when config maps to bone names FusionEngine will not read."""
        from .complementary_filter import JOINT_NAMES
        known = set(JOINT_NAMES)
        unknown = sorted({bone for bone in mapping.values() if bone not in known})
        if unknown:
            logger.warning(
                "Serial bone mapping contains unknown bone name(s) %s; "
                "these tracker ids will receive data but FusionEngine "
                "will never read them. Valid names: %s",
                unknown,
                sorted(known),
            )

    # ------------------------------------------------------------------
    # BaseIMUReceiver hooks
    # ------------------------------------------------------------------
    def _thread_name(self) -> str:
        return "serial-receiver"

    def start(self) -> None:
        super().start()
        logger.info(
            "SerialReceiver started (port=%s, baud=%d, %d tracker mappings)",
            self.port,
            self.baudrate,
            len(self.tracker_id_to_bone),
        )

    def stop(self) -> None:
        super().stop()
        logger.info("SerialReceiver stopped")

    def _on_stop_requested(self) -> None:
        """Close the serial handle so the blocking read wakes up.

        Detaches ``self._serial`` *before* closing it: the reader
        thread's finally-block rechecks ownership and skips the close
        when None, which is how we prevent a double-close race between
        stop() and the reader's own cleanup (regression from PR #11).
        """
        ser = self._serial
        self._serial = None
        if ser is not None:
            try:
                ser.close()
            except Exception:  # pragma: no cover - defensive
                pass

    def _run_loop(self) -> None:
        try:
            import serial  # noqa: F401  # type: ignore[import-not-found]
        except ImportError as exc:
            logger.error(
                "pyserial is not installed; install it with `pip install pyserial` "
                "or use --receiver osc. (%s)",
                exc,
            )
            self._running = False
            return

        buffer = b""
        while self._running:
            try:
                self._serial = _open_serial(self.port, self.baudrate)
            except Exception as exc:
                logger.warning(
                    "Serial open %s @ %d failed: %s (retrying in %.1fs)",
                    self.port,
                    self.baudrate,
                    exc,
                    self.reconnect_delay_sec,
                )
                self._sleep_interruptible(self.reconnect_delay_sec)
                continue

            logger.info("Serial port %s opened", self.port)
            try:
                while self._running:
                    ser = self._serial
                    if ser is None:
                        break
                    try:
                        chunk = ser.read(256)
                    except Exception as exc:
                        logger.warning("Serial read failed: %s", exc)
                        break
                    if not chunk:
                        continue
                    buffer += chunk
                    # DoS guard: drop the oldest bytes if the buffer grows
                    # beyond a reasonable resync window. A continuous
                    # garbage stream that never contains the sync pattern
                    # would otherwise accumulate indefinitely.
                    if len(buffer) > MAX_BUFFER_BYTES:
                        logger.warning(
                            "Serial buffer exceeded %d bytes without a sync "
                            "pattern; discarding oldest bytes.",
                            MAX_BUFFER_BYTES,
                        )
                        buffer = buffer[-FRAME_LENGTH:]
                    frames, buffer = parse_frames(buffer)
                    for tracker_id, payload in frames:
                        self._handle_frame(tracker_id, payload)
            finally:
                # stop() may have already detached and closed self._serial;
                # only close here if we still own the handle.
                ser = self._serial
                if ser is not None:
                    self._serial = None
                    try:
                        ser.close()
                    except Exception:  # pragma: no cover - defensive
                        pass

            if self._running:
                self._sleep_interruptible(self.reconnect_delay_sec)

    def _handle_frame(self, tracker_id: int, payload: bytes) -> None:
        """Decode a frame payload and publish the rotation."""
        bone_name = self.tracker_id_to_bone.get(tracker_id)
        if bone_name is None:
            return
        rotation = decode_rotation(payload)
        if rotation is None:
            return
        now = time.monotonic()
        self.bones[bone_name] = BoneData(rotation=rotation, timestamp=now)
        self._last_receive_time = now

    def _sleep_interruptible(self, seconds: float) -> None:
        """Sleep ``seconds`` but wake early if ``stop()`` has been called."""
        end = time.monotonic() + seconds
        while self._running and time.monotonic() < end:
            time.sleep(min(0.1, end - time.monotonic()))
