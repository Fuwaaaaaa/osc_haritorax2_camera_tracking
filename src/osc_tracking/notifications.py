"""Notification system — alerts for tracking issues.

Plays sounds and a system beep for:
- IMU disconnection / reconnection
- Camera lost / recovered
- Calibration drift detected
- Low FPS warning

Note: ``popup_enabled`` currently maps to a Windows ``MessageBeep`` — no
visual toast is shown. A future change may wire this to ``winotify`` or
``win10toast`` if optional-deps support is added. Callers should treat
popups as audible-only today.
"""

import logging
import threading

logger = logging.getLogger(__name__)

try:
    import winsound
    SOUND_AVAILABLE = True
except ImportError:
    SOUND_AVAILABLE = False


class NotificationType:
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


# Sound frequencies for different notification types
SOUNDS = {
    NotificationType.INFO: (800, 200),     # Short beep
    NotificationType.WARNING: (600, 400),  # Medium tone
    NotificationType.ERROR: (400, 600),    # Low long tone
}


class NotificationManager:
    """Manages tracking alerts and notifications."""

    def __init__(self, sound_enabled: bool = True, popup_enabled: bool = True):
        self.sound_enabled = sound_enabled
        self.popup_enabled = popup_enabled
        self._cooldowns: dict[str, float] = {}
        self._cooldown_sec = 10.0  # Don't repeat same notification within 10s

    def notify(self, message: str, level: str = NotificationType.INFO, tag: str = "") -> None:
        """Send a notification."""
        import time

        # Cooldown check
        if tag:
            now = time.monotonic()
            last = self._cooldowns.get(tag, 0)
            if now - last < self._cooldown_sec:
                return
            self._cooldowns[tag] = now

        logger.info("[%s] %s", level.upper(), message)

        if self.sound_enabled:
            self._play_sound(level)

        if self.popup_enabled:
            self._show_popup(message, level)

    def notify_disconnect(self) -> None:
        self.notify("IMU tracker disconnected", NotificationType.WARNING, "imu_disconnect")

    def notify_reconnect(self) -> None:
        self.notify("IMU tracker reconnected", NotificationType.INFO, "imu_reconnect")

    def notify_camera_lost(self, cam_id: int) -> None:
        self.notify(f"Camera {cam_id} lost", NotificationType.WARNING, f"cam_{cam_id}_lost")

    def notify_camera_recovered(self, cam_id: int) -> None:
        self.notify(f"Camera {cam_id} recovered", NotificationType.INFO, f"cam_{cam_id}_ok")

    def notify_calibration_drift(self) -> None:
        self.notify("Calibration may be off — consider recalibrating", NotificationType.WARNING, "calib_drift")

    def notify_low_fps(self, fps: float) -> None:
        self.notify(f"Low FPS: {fps:.0f}", NotificationType.WARNING, "low_fps")

    def _play_sound(self, level: str) -> None:
        if not SOUND_AVAILABLE:
            return
        freq, duration = SOUNDS.get(level, SOUNDS[NotificationType.INFO])
        threading.Thread(target=winsound.Beep, args=(freq, duration), daemon=True).start()  # type: ignore[attr-defined]

    def _show_popup(self, message: str, level: str) -> None:
        """Audible system notification (beep only — no toast UI today).

        Historically named ``popup`` and slated for a real toast via
        ``winotify``/``win10toast`` as an optional dep. See module docstring.
        """
        try:
            from ctypes import windll  # type: ignore[attr-defined]
            windll.user32.MessageBeep(0)  # System notification sound
        except Exception:
            pass
