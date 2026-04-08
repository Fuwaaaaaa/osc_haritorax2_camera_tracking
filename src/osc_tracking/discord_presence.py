"""Discord Rich Presence — show tracking status in Discord.

Requires: pypresence (optional dependency)
"""

import logging
import time

logger = logging.getLogger(__name__)

try:
    from pypresence import Presence
    DISCORD_AVAILABLE = True
except ImportError:
    DISCORD_AVAILABLE = False

# Register your own Discord app at https://discord.com/developers/applications
# This is a placeholder ID
DISCORD_APP_ID = "000000000000000000"


class DiscordPresence:
    """Updates Discord Rich Presence with tracking status."""

    def __init__(self, app_id: str = DISCORD_APP_ID):
        self._app_id = app_id
        self._rpc = None
        self._connected = False
        self._start_time = int(time.time())

    def start(self) -> None:
        if not DISCORD_AVAILABLE:
            logger.info("pypresence not installed — Discord integration disabled")
            return
        try:
            self._rpc = Presence(self._app_id)
            self._rpc.connect()
            self._connected = True
            self._rpc.update(
                state="Starting up...",
                details="OSC Tracking",
                start=self._start_time,
                large_image="tracking",
            )
            logger.info("Discord Rich Presence connected")
        except Exception as e:
            logger.debug("Discord connection failed (normal if Discord not running): %s", e)
            self._connected = False

    def update(self, mode: str, fps: float) -> None:
        if not self._connected or self._rpc is None:
            return
        try:
            self._rpc.update(
                state=f"Mode: {mode}",
                details=f"FPS: {fps:.0f}",
                start=self._start_time,
                large_image="tracking",
                small_image="green" if mode == "VISIBLE" else "yellow",
            )
        except Exception:
            self._connected = False

    def stop(self) -> None:
        if self._rpc and self._connected:
            try:
                self._rpc.close()
            except Exception:
                pass
        self._connected = False
