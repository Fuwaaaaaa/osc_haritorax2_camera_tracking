"""System tray quality meter — shows tracking state as green/yellow/red icon.

Requires: pystray, Pillow (both in dependencies)
"""

import logging
import threading
from enum import Enum

logger = logging.getLogger(__name__)

try:
    import pystray
    from PIL import Image, ImageDraw
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False


class QualityLevel(Enum):
    GOOD = "green"
    WARNING = "yellow"
    ERROR = "red"
    OFFLINE = "gray"


def _create_icon_image(color: str, size: int = 64) -> "Image.Image":
    """Create a solid circle icon."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    colors = {"green": "#22c55e", "yellow": "#eab308", "red": "#ef4444", "gray": "#6b7280"}
    draw.ellipse([4, 4, size - 4, size - 4], fill=colors.get(color, "#6b7280"))
    return img


class QualityMeter:
    """System tray icon showing tracking quality."""

    def __init__(self):
        self._icon: "pystray.Icon | None" = None
        self._thread: threading.Thread | None = None
        self._level = QualityLevel.OFFLINE
        self._fps = 0.0
        self._mode = "---"

    def start(self) -> None:
        if not TRAY_AVAILABLE:
            logger.warning("pystray not installed — quality meter disabled. pip install pystray")
            return

        menu = pystray.Menu(
            pystray.MenuItem("OSC Tracking", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(lambda item: f"Mode: {self._mode}", None, enabled=False),
            pystray.MenuItem(lambda item: f"FPS: {self._fps:.0f}", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._on_quit),
        )

        self._icon = pystray.Icon(
            "osc_tracking",
            _create_icon_image("gray"),
            "OSC Tracking",
            menu,
        )

        self._thread = threading.Thread(target=self._icon.run, daemon=True, name="tray-meter")
        self._thread.start()

    def update(self, level: QualityLevel, mode: str = "", fps: float = 0.0) -> None:
        if self._icon is None:
            return
        self._level = level
        self._mode = mode
        self._fps = fps
        try:
            self._icon.icon = _create_icon_image(level.value)
            self._icon.title = f"OSC Tracking — {mode} ({fps:.0f} fps)"
        except Exception:
            pass

    def stop(self) -> None:
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass
            self._icon = None

    def _on_quit(self, icon, item):
        icon.stop()
