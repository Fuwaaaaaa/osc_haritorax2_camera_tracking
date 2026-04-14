"""Tests for OBS overlay server."""

import json
import time
import urllib.request

import pytest

from osc_tracking.obs_overlay import OBSOverlay


@pytest.fixture
def overlay():
    ov = OBSOverlay(port=18767)
    ov.start()
    time.sleep(0.1)  # Let server bind
    yield ov
    ov.stop()


class TestOBSOverlay:
    def test_serves_html(self, overlay):
        resp = urllib.request.urlopen("http://localhost:18767/")
        html = resp.read().decode()
        assert "overlay" in html
        assert "mode" in html

    def test_state_endpoint_empty(self, overlay):
        resp = urllib.request.urlopen("http://localhost:18767/state")
        data = json.loads(resp.read())
        assert isinstance(data, dict)

    def test_state_updates(self, overlay):
        overlay.update(mode="VISIBLE", fps=30.0, avg_conf=0.85)
        resp = urllib.request.urlopen("http://localhost:18767/state")
        data = json.loads(resp.read())
        assert data["mode"] == "VISIBLE"
        assert data["fps"] == 30.0
        assert data["avg_conf"] == 0.85

    def test_threshold_injection(self, overlay):
        resp = urllib.request.urlopen("http://localhost:18767/")
        html = resp.read().decode()
        assert "0.7" in html  # visible_threshold
        assert "0.3" in html  # partial_threshold

    def test_cors_headers(self, overlay):
        resp = urllib.request.urlopen("http://localhost:18767/state")
        assert resp.headers.get("Access-Control-Allow-Origin") == "*"

    def test_404(self, overlay):
        try:
            urllib.request.urlopen("http://localhost:18767/nonexistent")
            assert False, "Should have raised"
        except urllib.error.HTTPError as e:
            assert e.code == 404

    def test_stop_and_restart(self):
        ov = OBSOverlay(port=18768)
        ov.start()
        time.sleep(0.1)
        ov.stop()
        # Should not raise
        ov2 = OBSOverlay(port=18768)
        ov2.start()
        time.sleep(0.1)
        resp = urllib.request.urlopen("http://localhost:18768/state")
        assert resp.status == 200
        ov2.stop()
