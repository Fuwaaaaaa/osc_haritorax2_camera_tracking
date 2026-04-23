"""Tests for the REST API HTTP layer.

Complements ``test_security_fixes.py`` (which focuses on CORS and
unauthenticated mutation guards) by exercising the happy path — GET
endpoints, ``update()`` ↔ ``/api/status`` round-trip, ``check_reset()``
toggle, and the 404 fallthrough.
"""

from __future__ import annotations

import json
import socket
import time
import urllib.request
from http.client import HTTPConnection

import pytest

from osc_tracking.config import TrackingConfig
from osc_tracking.rest_api import RestAPI


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_for(port: int, timeout: float = 3.0) -> None:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise TimeoutError(port)


@pytest.fixture
def api():
    # Clear the module-level state dict so tests don't see residue from
    # previous test runs (the state is a global in rest_api.py).
    from osc_tracking import rest_api as _mod
    _mod._state.clear()
    cfg = TrackingConfig()
    port = _free_port()
    a = RestAPI(port=port, config=cfg)
    a.start()
    _wait_for(port)
    yield a, port, cfg
    a.stop()


def _get(port: int, path: str) -> tuple[int, dict]:
    with urllib.request.urlopen(
        f"http://127.0.0.1:{port}{path}", timeout=2.0
    ) as resp:
        return resp.status, json.loads(resp.read().decode())


def test_status_endpoint_returns_state_after_update(api):
    a, port, _ = api
    a.update(mode="VISIBLE", fps=30.0, joints={"Hips": {"conf": 0.9}})
    status, body = _get(port, "/api/status")
    assert status == 200
    assert body["mode"] == "VISIBLE"
    assert body["fps"] == 30.0
    assert body["joints"]["Hips"]["conf"] == 0.9


def test_status_endpoint_reflects_subsequent_updates(api):
    a, port, _ = api
    a.update(mode="VISIBLE", fps=30.0)
    a.update(mode="PARTIAL_OCCLUSION", fps=25.0)
    _, body = _get(port, "/api/status")
    assert body["mode"] == "PARTIAL_OCCLUSION"
    assert body["fps"] == 25.0


def test_joints_endpoint_returns_only_joints(api):
    a, port, _ = api
    a.update(mode="VISIBLE", fps=30.0, joints={"Hips": {"conf": 0.9}, "Chest": {"conf": 0.8}})
    status, body = _get(port, "/api/joints")
    assert status == 200
    assert set(body.keys()) == {"Hips", "Chest"}


def test_joints_endpoint_empty_before_first_update(api):
    _, port, _ = api
    status, body = _get(port, "/api/joints")
    assert status == 200
    assert body == {}


def test_config_endpoint_returns_tracking_config_fields(api):
    _, port, cfg = api
    status, body = _get(port, "/api/config")
    assert status == 200
    # Smoke: a few known fields exist and match the live config object.
    assert body["target_fps"] == cfg.target_fps
    assert body["receiver_type"] == cfg.receiver_type


def test_config_endpoint_empty_when_no_config_attached():
    port = _free_port()
    a = RestAPI(port=port, config=None)
    a.start()
    try:
        _wait_for(port)
        status, body = _get(port, "/api/config")
        assert status == 200
        assert body == {}
    finally:
        a.stop()


def test_unknown_get_returns_404(api):
    _, port, _ = api
    conn = HTTPConnection("127.0.0.1", port, timeout=2.0)
    conn.request("GET", "/api/nope")
    resp = conn.getresponse()
    assert resp.status == 404
    conn.close()


def test_reset_post_sets_flag_and_check_reset_consumes_it(api):
    a, port, _ = api
    assert a.check_reset() is False  # initial
    conn = HTTPConnection("127.0.0.1", port, timeout=2.0)
    conn.request(
        "POST", "/api/reset",
        body=b"{}",
        headers={"Content-Type": "application/json"},
    )
    resp = conn.getresponse()
    conn.close()
    assert resp.status == 200
    assert a.check_reset() is True
    # Subsequent call sees the flag cleared.
    assert a.check_reset() is False


def test_unknown_post_returns_404(api):
    _, port, _ = api
    conn = HTTPConnection("127.0.0.1", port, timeout=2.0)
    conn.request(
        "POST", "/api/whatever",
        body=b"{}",
        headers={"Content-Type": "application/json"},
    )
    resp = conn.getresponse()
    assert resp.status == 404
    conn.close()
