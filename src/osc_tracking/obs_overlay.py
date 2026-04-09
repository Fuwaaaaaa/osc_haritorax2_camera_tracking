"""OBS overlay — WebSocket server for streaming tracking status to OBS.

Streams tracking state (mode, confidence, FPS) as JSON over a WebSocket
connection. OBS can display this using a Browser Source pointed at the
built-in overlay page.

Usage:
    overlay = OBSOverlay(port=8767)
    overlay.start()
    overlay.update(mode="VISIBLE", fps=30.0, avg_conf=0.85, joints={...})
    # OBS Browser Source: http://localhost:8767
"""

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

logger = logging.getLogger(__name__)

_overlay_state: dict = {}
_overlay_lock = threading.Lock()

OVERLAY_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:transparent;font-family:'Segoe UI',sans-serif;color:#fff;overflow:hidden}
.overlay{
  position:fixed;bottom:16px;left:16px;
  background:rgba(0,0,0,0.65);border-radius:8px;padding:10px 16px;
  backdrop-filter:blur(8px);min-width:200px;
  border:1px solid rgba(255,255,255,0.1)
}
.mode{font-size:14px;font-weight:700;margin-bottom:4px}
.stats{font-size:12px;opacity:0.8;display:flex;gap:12px}
.bar{height:4px;background:rgba(255,255,255,0.15);border-radius:2px;margin-top:6px}
.bar-fill{height:100%;border-radius:2px;transition:width 0.3s}
.good{color:#4ade80}.warn{color:#facc15}.bad{color:#f87171}
</style>
</head><body>
<div class="overlay" id="overlay">
  <div class="mode" id="mode">--</div>
  <div class="stats">
    <span id="fps">-- fps</span>
    <span id="conf">--%</span>
  </div>
  <div class="bar"><div class="bar-fill" id="bar"></div></div>
</div>
<script>
const VIS={visible_threshold};
const PAR={partial_threshold};
function poll(){
  fetch('/state').then(r=>r.json()).then(d=>{
    const m=document.getElementById('mode');
    m.textContent=d.mode||'--';
    m.className='mode '+(d.mode==='VISIBLE'?'good':
      d.mode==='FULL_OCCLUSION'||d.mode==='IMU_DISCONNECTED'?'bad':'warn');
    document.getElementById('fps').textContent=Math.round(d.fps||0)+' fps';
    const c=d.avg_conf||0;
    document.getElementById('conf').textContent=Math.round(c*100)+'%';
    const bar=document.getElementById('bar');
    bar.style.width=(c*100)+'%';
    bar.style.background=c>VIS?'#4ade80':c>PAR?'#facc15':'#f87171';
    if(!d.mode||d.mode==='--'){
      document.getElementById('overlay').style.opacity='0.3';
    }else{
      document.getElementById('overlay').style.opacity='1';
    }
  }).catch(()=>{});
  setTimeout(poll,500);
}
poll();
</script>
</body></html>"""


class OverlayHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(OVERLAY_HTML.encode())
        elif self.path == "/state":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            with _overlay_lock:
                self.wfile.write(json.dumps(_overlay_state).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


class OBSOverlay:
    """OBS-compatible overlay server for streaming tracking status."""

    def __init__(
        self,
        port: int = 8767,
        visible_threshold: float = 0.7,
        partial_threshold: float = 0.3,
    ):
        self.port = port
        self.visible_threshold = visible_threshold
        self.partial_threshold = partial_threshold
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        vis_th = self.visible_threshold
        par_th = self.partial_threshold

        class ConfiguredOverlayHandler(OverlayHandler):
            def do_GET(self):
                if self.path == "/":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    html = OVERLAY_HTML.replace(
                        "{visible_threshold}", str(vis_th)
                    ).replace(
                        "{partial_threshold}", str(par_th)
                    )
                    self.wfile.write(html.encode())
                else:
                    super().do_GET()

        self._server = HTTPServer(
            ("127.0.0.1", self.port), ConfiguredOverlayHandler
        )
        self._thread = threading.Thread(
            target=self._server.serve_forever, daemon=True, name="obs-overlay"
        )
        self._thread.start()
        logger.info(
            "OBS overlay running at http://localhost:%d (add as Browser Source)",
            self.port,
        )

    def update(
        self,
        mode: str,
        fps: float,
        avg_conf: float,
        joints: dict | None = None,
    ) -> None:
        with _overlay_lock:
            _overlay_state.update({
                "mode": mode,
                "fps": fps,
                "avg_conf": avg_conf,
                "joints": joints or {},
            })

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server = None
        self._thread = None
        logger.info("OBS overlay stopped")
