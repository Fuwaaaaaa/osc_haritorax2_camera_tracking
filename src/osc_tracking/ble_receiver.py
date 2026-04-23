"""Direct Bluetooth Low Energy receiver for HaritoraX2 IMU trackers.

EXPERIMENTAL. Bypasses SlimeTora + SlimeVR Server by connecting straight
to HaritoraX2 peripherals over BLE. Requires hardware for real validation.

Protocol reference (adapted from haritorax-interpreter, MIT licensed):
    https://github.com/JovannMC/haritorax-interpreter
    src/mode/bluetooth.ts (scan/connect flow)
    src/HaritoraX.ts::decodeIMUPacket (data layout)
    src/libs/common.ts (GATT UUIDs)

GATT
----
- Tracker Service:       ``00dbec3a-90aa-11ed-a1eb-0242ac120002``
- Sensor Characteristic: ``00dbf1c6-90aa-11ed-a1eb-0242ac120002`` (notify)

Sensor notification payload (14+ bytes, little-endian)::

    bytes 0-1:   rotationX  int16  * 0.01/180.0
    bytes 2-3:   rotationY  int16  * 0.01/180.0
    bytes 4-5:   rotationZ  int16  * -0.01/180.0   (sign flipped)
    bytes 6-7:   rotationW  int16  * -0.01/180.0   (sign flipped)
    bytes 8-13:  gravity x/y/z int16 * 1/256.0     (not used here; fusion rebuilds from rotation)
    bytes 14+:   optional ankle / mag bytes        (ignored)

Device model
------------
HaritoraX2 advertises one BLE peripheral per body-worn tracker with a
local name like ``HaritoraX2-<suffix>``. There is one Sensor characteristic
per peripheral, carrying that peripheral's rotation. Bone assignment is
configured externally via ``local_name_to_bone`` (the ``BodyPartAssignment``
characteristic read-back is a follow-up).

Threading
---------
bleak is asyncio-only. This module runs a dedicated asyncio event loop in
a background daemon thread. Notifications update ``self.bones`` directly
(key-level dict writes are atomic under the GIL). Reads on the main thread
go through ``get_bone_rotation`` (inherited from BaseIMUReceiver) with a
1-second staleness guard, matching the OSCReceiver contract.
"""

from __future__ import annotations

import asyncio
import logging
import struct
import time

from scipy.spatial.transform import Rotation

from .receiver_base import BaseIMUReceiver, BoneData

logger = logging.getLogger(__name__)

# Protocol constants (from haritorax-interpreter)
TRACKER_SERVICE_UUID = "00dbec3a-90aa-11ed-a1eb-0242ac120002"
SENSOR_CHAR_UUID = "00dbf1c6-90aa-11ed-a1eb-0242ac120002"
ROTATION_SCALAR = 0.01 / 180.0

# Default scan filter: only advertise names beginning with this string are considered.
DEFAULT_NAME_PREFIX = "HaritoraX2-"

# Seconds to wait for a fresh sample before is_connected flips to False.
FRESHNESS_WINDOW_SEC = 1.0

# Seconds to back off between scan/connect retries when a peripheral drops.
RECONNECT_DELAY_SEC = 5.0

# Re-exported so existing callers keep working after the base-class migration.
__all__ = [
    "BLEReceiver",
    "BoneData",
    "DEFAULT_NAME_PREFIX",
    "FRESHNESS_WINDOW_SEC",
    "RECONNECT_DELAY_SEC",
    "ROTATION_SCALAR",
    "SENSOR_CHAR_UUID",
    "TRACKER_SERVICE_UUID",
    "decode_rotation",
]


def decode_rotation(data: bytes) -> Rotation | None:
    """Decode a HaritoraX2 Sensor notification payload to a Rotation.

    Returns ``None`` for malformed packets (too short, non-finite values).
    The raw int16 Z and W components are sign-flipped per the reference
    implementation to match the expected quaternion handedness.
    """
    if len(data) < 8:
        logger.warning("BLE sensor payload too short: %d bytes", len(data))
        return None
    try:
        x_raw, y_raw, z_raw, w_raw = struct.unpack_from("<hhhh", data, 0)
    except struct.error as exc:
        logger.warning("BLE sensor payload unpack error: %s", exc)
        return None

    qx = x_raw * ROTATION_SCALAR
    qy = y_raw * ROTATION_SCALAR
    qz = -z_raw * ROTATION_SCALAR
    qw = -w_raw * ROTATION_SCALAR
    # Guard against a near-zero quaternion before calling scipy: older
    # Rotation.from_quat versions silently normalise (0,0,0,0) to the
    # identity rotation, which would look like a valid sample and
    # spuriously keep is_connected=True while bones freeze at identity.
    if abs(qx) + abs(qy) + abs(qz) + abs(qw) < 1e-9:
        logger.warning("BLE sensor payload decoded to zero quaternion; dropping frame")
        return None
    try:
        return Rotation.from_quat([qx, qy, qz, qw])
    except ValueError as exc:
        logger.warning("BLE sensor payload produced invalid quaternion: %s", exc)
        return None


class BLEReceiver(BaseIMUReceiver):
    """Receives IMU rotation data from HaritoraX2 peripherals over BLE.

    Parameters
    ----------
    local_name_to_bone
        Maps the BLE advertised local name of each peripheral to the
        skeleton bone name it represents (e.g. ``{"HaritoraX2-A1B2": "Hips"}``).
        Use the ``ble_scan`` tool to discover local names on your kit.
    name_prefix
        Scan filter: only devices whose advertised local name begins with
        this string are considered. Defaults to ``"HaritoraX2-"``.
    scan_timeout_sec
        How long each scan attempt runs before the connect loop retries.
    """

    def __init__(
        self,
        local_name_to_bone: dict[str, str] | None = None,
        name_prefix: str = DEFAULT_NAME_PREFIX,
        scan_timeout_sec: float = 10.0,
    ) -> None:
        super().__init__(freshness_window_sec=FRESHNESS_WINDOW_SEC)
        mapping = dict(local_name_to_bone or {})
        self.warn_on_unknown_bones(mapping.values(), "BLE")
        self.local_name_to_bone: dict[str, str] = mapping
        self.name_prefix = name_prefix
        self.scan_timeout_sec = float(scan_timeout_sec)

        self.bones = {
            bone: BoneData() for bone in self.local_name_to_bone.values()
        }
        self._loop: asyncio.AbstractEventLoop | None = None

    # ------------------------------------------------------------------
    # BaseIMUReceiver hooks
    # ------------------------------------------------------------------
    def _thread_name(self) -> str:
        return "ble-receiver"

    def start(self) -> None:
        super().start()
        logger.info(
            "BLEReceiver started (prefix=%r, %d bone mappings)",
            self.name_prefix,
            len(self.local_name_to_bone),
        )

    def stop(self) -> None:
        super().stop()
        self._loop = None
        logger.info("BLEReceiver stopped")

    def _on_stop_requested(self) -> None:
        """Wake the asyncio sleep so ``_ble_loop`` sees _running=False quickly."""
        loop = self._loop
        if loop is not None and loop.is_running():
            try:
                loop.call_soon_threadsafe(lambda: None)
            except RuntimeError:
                pass

    def _run_loop(self) -> None:
        """Entry point for the background daemon thread."""
        try:
            # Import bleak lazily so environments without BLE stack can still
            # import this module (e.g. CI that doesn't exercise BLEReceiver).
            import bleak  # noqa: F401
        except ImportError as exc:
            logger.error(
                "bleak is not installed; install it with `pip install bleak` "
                "or use --receiver osc. (%s)",
                exc,
            )
            self._running = False
            return

        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._ble_loop())
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("BLE event loop crashed: %s", exc)
        finally:
            try:
                loop.close()
            finally:
                self._loop = None

    async def _ble_loop(self) -> None:
        """Top-level scan -> connect -> subscribe retry loop."""
        from bleak import BleakScanner

        while self._running:
            try:
                devices = await BleakScanner.discover(timeout=self.scan_timeout_sec)
            except Exception as exc:
                logger.warning("BLE scan failed: %s (retrying in %.0fs)", exc, RECONNECT_DELAY_SEC)
                await self._sleep_interruptible(RECONNECT_DELAY_SEC)
                continue

            matches = []
            for d in devices:
                name = getattr(d, "name", None)
                if name and name.startswith(self.name_prefix):
                    matches.append(d)
            if not matches:
                logger.info(
                    "No %s* devices found; rescanning in %.0fs",
                    self.name_prefix,
                    RECONNECT_DELAY_SEC,
                )
                await self._sleep_interruptible(RECONNECT_DELAY_SEC)
                continue

            # Connect to every matching peripheral concurrently.
            tasks = [asyncio.create_task(self._handle_peripheral(d)) for d in matches]
            try:
                await asyncio.gather(*tasks, return_exceptions=True)
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception("Peripheral connection gather failed: %s", exc)

            if self._running:
                await self._sleep_interruptible(RECONNECT_DELAY_SEC)

    async def _handle_peripheral(self, device) -> None:
        """Connect to one peripheral and keep its notifications flowing."""
        from bleak import BleakClient

        local_name = device.name
        bone_name = self.local_name_to_bone.get(local_name)
        if bone_name is None:
            logger.info(
                "Discovered %s but no bone mapping configured; skipping", local_name
            )
            return

        try:
            async with BleakClient(device) as client:
                logger.info("Connected to %s (-> %s)", local_name, bone_name)

                def _on_notify(_sender, data: bytearray) -> None:
                    self._handle_sensor_data(bytes(data), bone_name)

                await client.start_notify(SENSOR_CHAR_UUID, _on_notify)
                while self._running and client.is_connected:
                    await asyncio.sleep(0.5)
                try:
                    await client.stop_notify(SENSOR_CHAR_UUID)
                except Exception:
                    pass
        except Exception as exc:
            logger.warning("BLE connection to %s failed: %s", local_name, exc)

    def _handle_sensor_data(self, data: bytes, bone_name: str) -> None:
        """Decode a Sensor notification and publish the rotation."""
        rotation = decode_rotation(data)
        if rotation is None:
            return
        now = time.monotonic()
        self.bones[bone_name] = BoneData(rotation=rotation, timestamp=now)
        self._last_receive_time = now

    async def _sleep_interruptible(self, seconds: float) -> None:
        """Sleep ``seconds`` but wake early if ``stop()`` has been called."""
        end = time.monotonic() + seconds
        while self._running and time.monotonic() < end:
            await asyncio.sleep(min(0.5, end - time.monotonic()))
