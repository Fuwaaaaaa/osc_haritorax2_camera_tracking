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


class APIHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/status":
            self._json_response(_state)
        elif self.path == "/api/config":
            if _config_ref:
                self._json_response(_config_ref.__dict__)
            else:
                self._json_response({})
        elif self.path == "/api/joints":
            with _lock:
                self._json_response(_state.get("joints", {}))
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'{"error":"not found"}')

    def do_POST(self):
        if self.path == "/api/reset":
            with _lock:
                _state["reset_requested"] = True
            self._json_response({"ok": True})
        elif self.path == "/api/config":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length > 0 else {}
            if _config_ref:
                for key, value in body.items():
                    if hasattr(_config_ref, key):
                        setattr(_config_ref, key, value)
            self._json_response({"ok": True})
        else:
            self.send_response(404)
            self.end_headers()

    def _json_response(self, data: dict) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
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
