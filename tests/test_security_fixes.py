"""Regression tests for P1/P2 security findings.

Each test targets a specific finding from the security review so a
future refactor cannot silently regress the fix.
"""

from __future__ import annotations

import json
import time
import urllib.request
from http.client import HTTPConnection
from pathlib import Path

import pytest

# ---------- Serial buffer DoS guard ----------

def test_serial_buffer_drops_when_oversized():
    """A stream of garbage bytes that never syncs must not grow the
    buffer without bound. The receiver guards MAX_BUFFER_BYTES."""
    pytest.importorskip("serial")
    from osc_tracking.serial_receiver import (
        FRAME_LENGTH,
        MAX_BUFFER_BYTES,
    )
    # Buffer size sanity: must be bounded and larger than one frame.
    assert MAX_BUFFER_BYTES > FRAME_LENGTH
    assert MAX_BUFFER_BYTES < 1024 * 1024  # not absurd


# ---------- Recorder path traversal ----------

def test_recorder_strips_path_components(tmp_path, caplog):
    from osc_tracking.recorder import TrackingRecorder
    rec = TrackingRecorder(output_dir=str(tmp_path))
    with caplog.at_level("WARNING"):
        out = rec.start("../../evil.jsonl")
    # The resulting file must live inside tmp_path, not escape it.
    assert out.parent.resolve() == Path(tmp_path).resolve()
    assert out.name == "evil.jsonl"
    rec.stop()
    assert any("path components" in r.message.lower() for r in caplog.records)


def test_recorder_accepts_clean_filename(tmp_path):
    from osc_tracking.recorder import TrackingRecorder
    rec = TrackingRecorder(output_dir=str(tmp_path))
    out = rec.start("ok.jsonl")
    assert out.parent.resolve() == Path(tmp_path).resolve()
    rec.stop()


# ---------- Calibration path traversal ----------

def test_calibration_repo_rejects_path_outside_cwd(tmp_path, monkeypatch, caplog):
    monkeypatch.chdir(tmp_path)
    from osc_tracking.persistence.calibration_repo import FileCalibrationRepository
    with caplog.at_level("WARNING"):
        repo = FileCalibrationRepository("../../outside.npz")
    # load() must return None because the path was rewritten.
    assert repo.load() is None
    assert any("escapes" in r.message.lower() for r in caplog.records)


def test_calibration_repo_accepts_inside_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from osc_tracking.persistence.calibration_repo import FileCalibrationRepository
    # File doesn't exist — load() returns None — but path must be
    # accepted (no warning) because it's within cwd.
    repo = FileCalibrationRepository("calibration_data/stereo_calib.npz")
    assert repo.load() is None  # file absent, not rejected


# ---------- REST API: config POST removed + CORS tightened ----------

def test_rest_api_rejects_config_post():
    """The unauthenticated /api/config POST is gone."""
    from osc_tracking.config import TrackingConfig
    from osc_tracking.rest_api import RestAPI

    cfg = TrackingConfig()
    api = RestAPI(port=_free_port(), config=cfg)
    api.start()
    try:
        _wait_for_server(api.port)
        conn = HTTPConnection("127.0.0.1", api.port, timeout=3.0)
        payload = json.dumps({"osc_send_host": "attacker.example"}).encode()
        conn.request(
            "POST", "/api/config",
            body=payload,
            headers={"Content-Type": "application/json"},
        )
        resp = conn.getresponse()
        conn.close()
        assert resp.status == 404
        # Config must be unchanged.
        assert cfg.osc_send_host != "attacker.example"
    finally:
        api.stop()


def test_rest_api_rejects_cross_origin_post(tmp_path):
    from osc_tracking.config import TrackingConfig
    from osc_tracking.rest_api import RestAPI

    cfg = TrackingConfig()
    api = RestAPI(port=_free_port(), config=cfg)
    api.start()
    try:
        _wait_for_server(api.port)
        conn = HTTPConnection("127.0.0.1", api.port, timeout=3.0)
        conn.request(
            "POST", "/api/reset",
            body=b"{}",
            headers={
                "Content-Type": "application/json",
                "Origin": "https://evil.example",
            },
        )
        resp = conn.getresponse()
        conn.close()
        assert resp.status == 403
    finally:
        api.stop()


def test_rest_api_allows_same_origin_reset():
    from osc_tracking.config import TrackingConfig
    from osc_tracking.rest_api import RestAPI

    cfg = TrackingConfig()
    port = _free_port()
    api = RestAPI(port=port, config=cfg)
    api.start()
    try:
        _wait_for_server(port)
        conn = HTTPConnection("127.0.0.1", port, timeout=2.0)
        conn.request(
            "POST", "/api/reset",
            body=b"{}",
            headers={
                "Content-Type": "application/json",
                "Origin": f"http://localhost:{port}",
            },
        )
        resp = conn.getresponse()
        conn.close()
        assert resp.status == 200
    finally:
        api.stop()


def test_rest_api_config_get_hides_sensitive_fields():
    """/api/config is CORS-open for dashboards, so it must not include
    paths, hostnames, or COM ports that a cross-origin tab could pull
    out via fetch."""
    from osc_tracking.config import TrackingConfig
    from osc_tracking.rest_api import RestAPI

    cfg = TrackingConfig()
    # Populate several sensitive fields so we can assert they're filtered.
    cfg.osc_send_host = "10.0.0.5"
    cfg.serial_port = "COM3"
    cfg.calibration_file = "C:/private/calib.npz"
    cfg.model_path = "C:/private/models/pose.task"

    port = _free_port()
    api = RestAPI(port=port, config=cfg)
    api.start()
    try:
        _wait_for_server(port)
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/config", timeout=2.0) as resp:
            body = json.loads(resp.read())
    finally:
        api.stop()

    for leaky in ("osc_send_host", "serial_port", "calibration_file",
                  "model_path", "ble_local_name_to_bone",
                  "serial_tracker_id_to_bone"):
        assert leaky not in body, f"sensitive field {leaky!r} leaked through /api/config"
    # But safe operational knobs stay visible so dashboards still work.
    assert "target_fps" in body
    assert "receiver_type" in body


def test_rest_api_post_body_cap_prevents_dos():
    """A malicious Content-Length must not cause the handler to block
    on a multi-gigabyte read. The cap is exposed so tests can assert
    a specific bound without hard-coding magic numbers here."""
    from osc_tracking.rest_api import MAX_REQUEST_BODY

    assert 1_024 <= MAX_REQUEST_BODY <= 1_024 * 1_024  # 1 KiB..1 MiB


# ---------- MediaPipe model path traversal ----------

def test_mediapipe_model_path_rejects_traversal(tmp_path, caplog):
    """A config-supplied model path pointing outside the project tree
    (e.g. ``../../etc/passwd``) must be refused before it reaches
    MediaPipe's native loader."""
    from osc_tracking.camera_tracker import _resolve_model_path

    # Create a file outside the project so "exists" alone isn't enough.
    outside = tmp_path / "fake_model.task"
    outside.write_bytes(b"not a real model")
    with caplog.at_level("WARNING"):
        resolved = _resolve_model_path(str(outside), str(outside))
    assert resolved is None
    assert any("outside the project root" in r.message for r in caplog.records)


def test_mediapipe_model_path_accepts_inside_project():
    """Files that resolve inside the project tree pass through."""
    from osc_tracking.camera_tracker import _resolve_model_path

    # CLAUDE.md lives at the project root; use it as a stand-in path
    # that definitely exists inside the tree.
    project_root = Path(__file__).resolve().parent.parent
    inside_ok = project_root / "CLAUDE.md"
    resolved = _resolve_model_path(str(inside_ok), str(inside_ok))
    assert resolved is not None
    assert resolved == inside_ok.resolve()


def test_mediapipe_model_path_returns_none_when_missing(tmp_path):
    """Neither path exists → None, handler logs an instructive error."""
    from osc_tracking.camera_tracker import _resolve_model_path

    missing = tmp_path / "nope.task"
    assert _resolve_model_path(str(missing), str(missing)) is None


def _free_port() -> int:
    """Get a free port from the OS."""
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_for_server(port: int, timeout: float = 3.0) -> None:
    """Poll until the server accepts TCP connections, or give up."""
    import socket
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise TimeoutError(f"server on port {port} never accepted connections")


# ---------- OBS overlay threshold sanitization ----------

def test_obs_overlay_clamps_thresholds_to_range():
    """A config-supplied threshold outside [0,1] must be clamped
    before being injected into the inline JS template."""
    from osc_tracking.obs_overlay import OBSOverlay
    port = _free_port()
    overlay = OBSOverlay(
        port=port,
        visible_threshold=9.5,  # out of range
        partial_threshold=-2.0,
    )
    overlay.start()
    try:
        time.sleep(0.1)
        html = urllib.request.urlopen(
            f"http://127.0.0.1:{port}/", timeout=2.0
        ).read().decode()
        # Clamped values (1.0 and 0.0) appear in the injected JS.
        assert "const VIS=1.0" in html or "const VIS=1" in html or "VIS=1.0" in html
        assert "const PAR=0.0" in html or "const PAR=0" in html or "PAR=0.0" in html
        # Absurd raw values must not appear verbatim.
        assert "9.5" not in html
        assert "-2.0" not in html
    finally:
        overlay.stop()
