"""Tests for resource path resolution (dev vs PyInstaller exe)."""

import sys
from pathlib import Path
from unittest.mock import patch

from osc_tracking import paths


class TestResourceRoot:
    def test_dev_mode_returns_project_root(self):
        """In dev (not frozen), root should be the project directory."""
        with patch.object(sys, "frozen", False, create=True):
            root = paths.get_resource_root()
        assert root.is_dir()
        # Project root should contain config/ in normal dev layout
        # (we just assert Path type — not hard-coding cwd)
        assert isinstance(root, Path)

    def test_frozen_exe_prefers_executable_dir(self, tmp_path, monkeypatch):
        """For frozen exe, resolve next to sys.executable (where copy_config_to_dist puts things)."""
        fake_exe = tmp_path / "osc_tracking.exe"
        fake_exe.write_bytes(b"")
        (tmp_path / "config").mkdir()

        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "executable", str(fake_exe))

        root = paths.get_resource_root()
        assert root == tmp_path

    def test_frozen_falls_back_to_meipass_when_no_exe_config(
        self, tmp_path, monkeypatch
    ):
        """If exe-adjacent config/ is missing, fall back to _MEIPASS (bundle)."""
        meipass_dir = tmp_path / "meipass"
        meipass_dir.mkdir()
        (meipass_dir / "config").mkdir()

        exe_dir = tmp_path / "bin"
        exe_dir.mkdir()
        fake_exe = exe_dir / "osc_tracking.exe"
        fake_exe.write_bytes(b"")

        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "executable", str(fake_exe))
        monkeypatch.setattr(sys, "_MEIPASS", str(meipass_dir), raising=False)

        root = paths.get_resource_root()
        assert root == meipass_dir


class TestConfigDir:
    def test_config_dir_is_under_resource_root(self):
        assert paths.config_dir().name == "config"
        assert paths.config_dir().parent == paths.get_resource_root()

    def test_default_config_path(self):
        assert paths.default_config_path().name == "default.json"
        assert paths.default_config_path().parent == paths.config_dir()

    def test_user_config_path(self):
        assert paths.user_config_path().name == "user.json"
