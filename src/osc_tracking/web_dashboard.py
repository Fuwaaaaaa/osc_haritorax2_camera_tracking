"""Web monitoring dashboard — real-time tracking status in browser.

Runs a lightweight HTTP server that serves a live dashboard showing
confidence, mode, FPS, and per-joint status via Server-Sent Events.

Usage: Integrate with FusionEngine, then open http://localhost:8765
"""

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

logger = logging.getLogger(__name__)

_latest_state: dict = {}
_lock = threading.Lock()

DASHBOARD_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>OSC Tracking Dashboard</title>
<style>
body{font-family:system-ui;background:#111;color:#eee;margin:2em;max-width:800px}
h1{color:#8b5cf6}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:1em;margin:1em 0}
.card{background:#1e1e2e;border-radius:8px;padding:1em;text-align:center}
.card .value{font-size:2em;font-weight:bold}
.green{color:#22c55e}.yellow{color:#eab308}.red{color:#ef4444}.gray{color:#6b7280}
.joint{background:#1e1e2e;border-radius:4px;padding:0.5em;margin:0.2em 0;
  display:flex;justify-content:space-between}
.bar{height:8px;background:#333;border-radius:4px;flex:1;margin-left:1em}
.bar-fill{height:100%;border-radius:4px;transition:width 0.3s}
#log{background:#0a0a0a;padding:1em;border-radius:8px;max-height:200px;
  overflow-y:auto;font-family:monospace;font-size:0.85em}
</style></head><body>
<h1>OSC Tracking Dashboard</h1>
<div class="grid">
  <div class="card"><div>Mode</div><div class="value" id="mode">---</div></div>
  <div class="card"><div>FPS</div><div class="value" id="fps">0</div></div>
  <div class="card"><div>Confidence</div><div class="value" id="conf">0%</div></div>
</div>
<h2>Joints</h2>
<div id="joints"></div>
<h2>Log</h2>
<div id="log"></div>
<script>
const es=new EventSource('/events');
es.onmessage=e=>{
  const d=JSON.parse(e.data);
  document.getElementById('mode').textContent=d.mode||'---';
  document.getElementById('mode').className='value '+(
    d.mode==='VISIBLE'?'green':d.mode==='FULL_OCCLUSION'?'red':'yellow');
  document.getElementById('fps').textContent=Math.round(d.fps||0);
  document.getElementById('conf').textContent=Math.round((d.avg_conf||0)*100)+'%';
  const jc=document.getElementById('joints');
  if(d.joints){
    jc.innerHTML='';
    for(const[name,j]of Object.entries(d.joints)){
      const c=j.conf>0.7?'#22c55e':j.conf>0.3?'#eab308':'#ef4444';
      jc.innerHTML+=`<div class="joint"><span>${name}</span>
        <div class="bar"><div class="bar-fill" style="width:${j.conf*100}%;background:${c}"></div></div>
        <span style="width:3em;text-align:right">${(j.conf*100).toFixed(0)}%</span></div>`;
    }
  }
  const log=document.getElementById('log');
  log.innerHTML+=d.mode+' conf='+((d.avg_conf||0)*100).toFixed(0)+'%\\n';
  log.scrollTop=log.scrollHeight;
};
</script></body></html>"""


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(DASHBOARD_HTML.encode())
        elif self.path == "/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            import time
            try:
                while True:
                    with _lock:
                        data = json.dumps(_latest_state)
                    self.wfile.write(f"data: {data}\n\n".encode())
                    self.wfile.flush()
                    time.sleep(0.5)
            except (BrokenPipeError, ConnectionResetError):
                pass
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress HTTP logs


class WebDashboard:
    """Lightweight web dashboard for tracking monitoring."""

    def __init__(self, port: int = 8765):
        self.port = port
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._server = HTTPServer(("127.0.0.1", self.port), DashboardHandler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True, name="web-dashboard")
        self._thread.start()
        logger.info("Dashboard running at http://localhost:%d", self.port)

    def update(self, mode: str, fps: float, avg_conf: float, joints: dict | None = None) -> None:
        with _lock:
            _latest_state.update({
                "mode": mode,
                "fps": round(fps, 1),
                "avg_conf": round(avg_conf, 3),
                "joints": joints or {},
            })

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server = None
