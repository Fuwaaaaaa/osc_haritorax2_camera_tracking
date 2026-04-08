"""Hotkey system — keyboard shortcuts for common actions.

Uses pynput for global keyboard hooks (optional dependency).
Falls back to no-op if pynput is not installed.
"""

import logging

logger = logging.getLogger(__name__)

try:
    from pynput import keyboard
    HOTKEYS_AVAILABLE = True
except ImportError:
    HOTKEYS_AVAILABLE = False


class HotkeyManager:
    """Global hotkey bindings for tracking control."""

    DEFAULT_BINDINGS = {
        "<f5>": "reset",        # Reset coordinate system
        "<f6>": "calibrate",    # Trigger recalibration
        "<f7>": "record_toggle",  # Start/stop recording
        "<f8>": "mode_cycle",   # Cycle through motion presets
        "<f9>": "pause_toggle", # Pause/resume tracking
    }

    def __init__(self, bindings: dict[str, str] | None = None):
        self._bindings = bindings or self.DEFAULT_BINDINGS
        self._callbacks: dict[str, list] = {}
        self._listener = None

    def on(self, action: str, callback) -> None:
        self._callbacks.setdefault(action, []).append(callback)

    def start(self) -> None:
        if not HOTKEYS_AVAILABLE:
            logger.info("pynput not installed — hotkeys disabled. pip install pynput")
            return

        def on_press(key):
            key_str = str(key).strip("'")
            for binding, action in self._bindings.items():
                if key_str == binding or (hasattr(key, 'name') and f"<{key.name}>" == binding):
                    self._fire(action)

        listener = keyboard.Listener(on_press=on_press)
        listener.daemon = True  # type: ignore[attr-defined]
        listener.start()
        self._listener = listener
        logger.info("Hotkeys active: %s", ", ".join(f"{k}→{v}" for k, v in self._bindings.items()))

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
            self._listener = None

    def _fire(self, action: str) -> None:
        for cb in self._callbacks.get(action, []):
            try:
                cb()
            except Exception:
                logger.exception("Hotkey callback failed for %s", action)
