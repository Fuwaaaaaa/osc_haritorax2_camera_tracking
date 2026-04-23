"""REST API — HTTP endpoints for external integrations.

Provides JSON API for reading tracking state and changing settings.
Uses stdlib http.server (no Flask/FastAPI dependency).
"""

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

logger = logging.getLogger(__name__)

_state: dict = {}
_config_ref = None
_lock = threading.Lock()

# Cap POST bodies so a local process claiming a huge Content-Length can't
# pin the rest-api thread on a long blocking read. 64 KiB is ~1000x any
# legitimate control payload we send.
MAX_REQUEST_BODY = 65_536

# Config fields safe to expose to dashboards. Anything carrying paths,
# hostnames, or COM port names stays server-side so a page loaded in the
# user's browser on any site can't exfiltrate it via the CORS-open
# GET /api/config endpoint.
_CONFIG_PUBLIC_FIELDS = frozenset({
    "target_fps",
    "camera_resolution",
    "visible_threshold",
    "partial_threshold",
    "smooth_rate",
    "compass_blend_factor",
    "pose_predictor_enabled",
    "refine_triangulation",
    "receiver_type",
    "cam_indices",
    "cam1_index",
    "cam2_index",
    "futon_pitch_threshold",
    "futon_exit_threshold",
    "futon_dwell_time_sec",
    "futon_trigger_joint",
})


def _public_config_view(config: object) -> dict:
    """Return only the config fields safe for cross-origin readers."""
    if config is None:
        return {}
    attrs = getattr(config, "__dict__", {})
    return {k: v for k, v in attrs.items() if k in _CONFIG_PUBLIC_FIELDS}


class APIHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/status":
            self._json_response(_state)
        elif self.path == "/api/config":
            self._json_response(_public_config_view(_config_ref))
        elif self.path == "/api/joints":
            with _lock:
                self._json_response(_state.get("joints", {}))
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'{"error":"not found"}')

    def do_POST(self):
        # Drain the request body regardless of what we do with it — on
        # Windows, responding before reading causes the client to see
        # a connection abort rather than the HTTP status. Cap the read
        # at MAX_REQUEST_BODY so a bogus Content-Length can't occupy
        # the handler thread on a multi-gigabyte stream.
        declared = int(self.headers.get("Content-Length", 0))
        length = min(declared, MAX_REQUEST_BODY)
        if length > 0:
            try:
                self.rfile.read(length)
            except Exception:
                pass

        # Reject cross-origin mutating requests. ``http.server`` does not
        # enforce Origin checks, so a browser tab on any other site could
        # otherwise CSRF the local API. Any browser issuing a cross-origin
        # POST will set Origin; same-origin tools (curl, scripts) typically
        # do not, and those are what legitimate callers look like.
        origin = self.headers.get("Origin", "")
        if origin and origin not in (
            f"http://localhost:{self.server.server_address[1]}",
            f"http://127.0.0.1:{self.server.server_address[1]}",
        ):
            self.send_response(403)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":"forbidden origin"}')
            return

        if self.path == "/api/reset":
            with _lock:
                _state["reset_requested"] = True
            self._json_response({"ok": True}, allow_cors=False)
        else:
            # /api/config POST was removed: it allowed any local browser
            # tab to rewrite arbitrary TrackingConfig fields (e.g. redirect
            # osc_send_host). Runtime config changes should go through the
            # in-app setup wizard or a config file reload, not HTTP.
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":"not found"}')

    def _json_response(self, data: dict, *, allow_cors: bool = True) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        if allow_cors:
            # Read-only endpoints keep CORS open for dashboards.
            self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, default=str).encode())

    def log_message(self, format, *args):
        pass


class RestAPI:
    """REST API server for tracking control."""

    def __init__(self, port: int = 8766, config=None):
        global _config_ref
        self.port = port
        _config_ref = config
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._server = HTTPServer(("127.0.0.1", self.port), APIHandler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True, name="rest-api")
        self._thread.start()
        logger.info("REST API at http://localhost:%d/api/", self.port)

    def update(self, mode: str, fps: float, joints: dict | None = None) -> None:
        with _lock:
            _state.update({"mode": mode, "fps": fps, "joints": joints or {}})

    def check_reset(self) -> bool:
        with _lock:
            if _state.get("reset_requested"):
                _state["reset_requested"] = False
                return True
        return False

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
