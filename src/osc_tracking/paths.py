"""Resource path resolution for dev and PyInstaller builds.

PyInstaller freezes the app in two layouts that we care about:

1. ``sys.executable``'s directory — where ``build_exe.py``'s
   ``copy_config_to_dist`` places ``config/`` next to the exe so users
   can edit it. This is the canonical location for user-editable files.
2. ``sys._MEIPASS`` — the temp bundle directory that PyInstaller extracts
   read-only assets (models, bundled default.json) into at runtime.

In dev mode the project root (this file's parents[2]) holds both.

``get_resource_root`` picks the first layout that actually contains
``config/``; if neither does, returns the exe dir (or project root in dev)
so callers get a consistent Path they can create files under.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _project_root() -> Path:
    # src/osc_tracking/paths.py → project root is parents[2]
    return Path(__file__).resolve().parents[2]


def get_resource_root() -> Path:
    """Return the directory that ``config/``, ``models/``, etc. resolve against."""
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        if (exe_dir / "config").is_dir():
            return exe_dir
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return exe_dir
    return _project_root()


def config_dir() -> Path:
    return get_resource_root() / "config"


def default_config_path() -> Path:
    return config_dir() / "default.json"


def user_config_path() -> Path:
    return config_dir() / "user.json"
