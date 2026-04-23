"""Tests for NotificationManager.

Mocks the audio / popup side effects (``winsound.Beep``,
``ctypes.windll.user32.MessageBeep``) so the tests run silently and
cross-platform. The public API — cooldown logic, convenience methods,
and enabled-flag gating — is what actually matters.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from osc_tracking.notifications import (
    SOUNDS,
    NotificationManager,
    NotificationType,
)


@pytest.fixture
def silent_manager():
    """Manager with sound + popup paths stubbed to no-ops."""
    mgr = NotificationManager(sound_enabled=True, popup_enabled=True)
    mgr._play_sound = MagicMock()  # type: ignore[method-assign]
    mgr._show_popup = MagicMock()  # type: ignore[method-assign]
    return mgr


def test_notify_logs_message(silent_manager, caplog):
    caplog.set_level("INFO")
    silent_manager.notify("hello", NotificationType.INFO)
    assert any("hello" in r.message for r in caplog.records)


def test_notify_triggers_sound_when_enabled(silent_manager):
    silent_manager.notify("test", NotificationType.WARNING)
    silent_manager._play_sound.assert_called_once_with(NotificationType.WARNING)


def test_notify_triggers_popup_when_enabled(silent_manager):
    silent_manager.notify("test", NotificationType.INFO)
    silent_manager._show_popup.assert_called_once()


def test_sound_disabled_skips_beep():
    mgr = NotificationManager(sound_enabled=False, popup_enabled=True)
    mgr._play_sound = MagicMock()  # type: ignore[method-assign]
    mgr._show_popup = MagicMock()  # type: ignore[method-assign]
    mgr.notify("quiet", NotificationType.INFO)
    mgr._play_sound.assert_not_called()
    mgr._show_popup.assert_called_once()


def test_popup_disabled_skips_popup():
    mgr = NotificationManager(sound_enabled=True, popup_enabled=False)
    mgr._play_sound = MagicMock()  # type: ignore[method-assign]
    mgr._show_popup = MagicMock()  # type: ignore[method-assign]
    mgr.notify("no-popup", NotificationType.INFO)
    mgr._show_popup.assert_not_called()


def test_cooldown_suppresses_repeated_tag(silent_manager):
    """Within the cooldown window, the same tag fires once."""
    silent_manager.notify("first", NotificationType.INFO, tag="same")
    silent_manager.notify("second", NotificationType.INFO, tag="same")
    assert silent_manager._play_sound.call_count == 1


def test_cooldown_does_not_apply_across_tags(silent_manager):
    silent_manager.notify("a", NotificationType.INFO, tag="tag1")
    silent_manager.notify("b", NotificationType.INFO, tag="tag2")
    assert silent_manager._play_sound.call_count == 2


def test_cooldown_lifts_after_window(silent_manager):
    silent_manager._cooldown_sec = 0.05
    silent_manager.notify("a", NotificationType.INFO, tag="same")
    time.sleep(0.1)
    silent_manager.notify("b", NotificationType.INFO, tag="same")
    assert silent_manager._play_sound.call_count == 2


def test_notify_disconnect_uses_warning_level(silent_manager):
    silent_manager.notify_disconnect()
    silent_manager._play_sound.assert_called_once_with(NotificationType.WARNING)


def test_notify_reconnect_uses_info_level(silent_manager):
    silent_manager.notify_reconnect()
    silent_manager._play_sound.assert_called_once_with(NotificationType.INFO)


def test_notify_camera_lost_includes_id_in_tag(silent_manager):
    """Per-camera tags isolate cooldowns between different cameras."""
    silent_manager.notify_camera_lost(0)
    silent_manager.notify_camera_lost(1)  # different cam → not cooled down
    assert silent_manager._play_sound.call_count == 2


def test_notify_camera_recovered_uses_info_level(silent_manager):
    silent_manager.notify_camera_recovered(0)
    silent_manager._play_sound.assert_called_once_with(NotificationType.INFO)


def test_notify_calibration_drift_uses_warning_level(silent_manager):
    silent_manager.notify_calibration_drift()
    silent_manager._play_sound.assert_called_once_with(NotificationType.WARNING)


def test_notify_low_fps_formats_value(silent_manager, caplog):
    caplog.set_level("INFO")
    silent_manager.notify_low_fps(12.345)
    # Formatted with :.0f = "12"
    assert any("Low FPS: 12" in r.message for r in caplog.records)


def test_sounds_table_has_entry_for_every_level():
    for level in (NotificationType.INFO, NotificationType.WARNING, NotificationType.ERROR):
        assert level in SOUNDS


def test_play_sound_noop_when_winsound_unavailable(monkeypatch):
    """On Linux/macOS the module-level ``SOUND_AVAILABLE`` flag is False;
    _play_sound should quietly skip rather than crash."""
    from osc_tracking import notifications
    monkeypatch.setattr(notifications, "SOUND_AVAILABLE", False)
    mgr = NotificationManager()
    mgr._play_sound(NotificationType.INFO)  # must not raise


def test_show_popup_swallows_import_errors(silent_manager):
    """_show_popup catches ctypes failures so non-Windows hosts don't crash."""
    real_mgr = NotificationManager()
    # Patch ctypes import to fail inside _show_popup.
    with patch("ctypes.windll", create=True, new=None):
        real_mgr._show_popup("msg", NotificationType.INFO)  # must not raise
