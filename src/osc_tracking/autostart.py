"""Windows auto-start — launch OSC Tracking on login.

Creates/removes a shortcut in the Windows Startup folder.
"""

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def get_startup_folder() -> Path:
    """Get the Windows Startup folder path."""
    import os
    appdata = os.environ.get("APPDATA", "")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def enable_autostart(script_args: str = "") -> bool:
    """Add OSC Tracking to Windows startup."""
    startup = get_startup_folder()
    if not startup.exists():
        logger.error("Startup folder not found: %s", startup)
        return False

    bat_path = startup / "osc_tracking.bat"
    python_path = sys.executable
    module_cmd = f'"{python_path}" -m osc_tracking.main {script_args}'

    bat_path.write_text(f"@echo off\n{module_cmd}\n", encoding="utf-8")
    logger.info("Auto-start enabled: %s", bat_path)
    return True


def disable_autostart() -> bool:
    """Remove OSC Tracking from Windows startup."""
    startup = get_startup_folder()
    bat_path = startup / "osc_tracking.bat"

    if bat_path.exists():
        bat_path.unlink()
        logger.info("Auto-start disabled")
        return True

    logger.info("Auto-start was not enabled")
    return False


def is_autostart_enabled() -> bool:
    """Check if auto-start is currently enabled."""
    startup = get_startup_folder()
    return (startup / "osc_tracking.bat").exists()
