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
<html lang="ja"><head><meta charset="utf-8"><title>OSC Tracking Dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{
  --bg-base:#0a0a0f;--bg-surface:#12121a;--bg-elevated:#1a1a26;--bg-hover:#22222e;
  --text-primary:#e8e8ed;--text-secondary:#9898a8;--text-muted:#5a5a6e;
  --accent:#06b6d4;--accent-glow:rgba(6,182,212,0.15);
  --green:#22c55e;--yellow:#eab308;--red:#ef4444;--border:#2a2a38;
  --font-body:'Geist',system-ui,sans-serif;--font-mono:'JetBrains Mono',monospace;
}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:var(--font-body);background:var(--bg-base);color:var(--text-primary);
  padding:24px;max-width:960px;margin:0 auto;-webkit-font-smoothing:antialiased}
body::before{content:'';position:fixed;inset:0;
  background:linear-gradient(rgba(6,182,212,0.03) 1px,transparent 1px),
  linear-gradient(90deg,rgba(6,182,212,0.03) 1px,transparent 1px);
  background-size:48px 48px;pointer-events:none;z-index:0}
body>*{position:relative;z-index:1}
h1{font-family:var(--font-body);font-weight:700;font-size:1.1rem;color:var(--accent);
  padding:16px 0;border-bottom:1px solid var(--border);margin-bottom:16px;
  display:flex;align-items:center;justify-content:space-between}
h1 .status{font-family:var(--font-mono);font-size:0.8rem;display:flex;align-items:center;gap:8px}
h1 .status::before{content:'';width:8px;height:8px;border-radius:50%;
  background:var(--green);box-shadow:0 0 8px var(--green)}
h2{font-family:var(--font-mono);font-weight:500;font-size:0.7rem;text-transform:uppercase;
  letter-spacing:0.08em;color:var(--text-muted);margin:24px 0 8px}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:16px}
.card{background:var(--bg-surface);border:1px solid var(--border);border-radius:8px;padding:16px}
.card-label{font-family:var(--font-mono);font-size:0.7rem;text-transform:uppercase;
  letter-spacing:0.08em;color:var(--text-muted);margin-bottom:4px}
.card-value{font-family:var(--font-mono);font-size:1.8rem;font-weight:700;
  font-variant-numeric:tabular-nums}
.card-unit{font-size:0.8rem;font-weight:400;color:var(--text-muted);margin-left:2px}
.green{color:var(--green)}.yellow{color:var(--yellow)}.red{color:var(--red)}
.cyan{color:var(--accent)}
.joint{background:var(--bg-surface);border:1px solid var(--border);border-radius:4px;
  padding:8px 12px;margin:3px 0;display:flex;align-items:center;gap:12px}
.joint-name{font-family:var(--font-mono);font-size:0.8rem;width:100px;color:var(--text-secondary)}
.bar{flex:1;height:6px;background:var(--bg-hover);border-radius:3px;overflow:hidden}
.bar-fill{height:100%;border-radius:3px;transition:width 0.3s ease-out}
.joint-conf{font-family:var(--font-mono);font-size:0.75rem;width:80px;text-align:right;
  font-variant-numeric:tabular-nums}
#log{background:var(--bg-surface);border:1px solid var(--border);padding:12px;
  border-radius:8px;max-height:160px;overflow-y:auto;
  font-family:var(--font-mono);font-size:0.75rem;line-height:1.8;color:var(--text-muted)}
.log-mode{color:var(--accent)}.log-val{color:var(--text-primary)}
</style></head><body>
<h1>OSC Tracking<span class="status" id="status">Waiting...</span></h1>
<div class="grid">
  <div class="card"><div class="card-label">Mode</div>
    <div class="card-value" id="mode">---</div></div>
  <div class="card"><div class="card-label">FPS</div>
    <div class="card-value cyan" id="fps">0</div></div>
  <div class="card"><div class="card-label">Confidence</div>
    <div class="card-value" id="conf">0<span class="card-unit">%</span></div></div>
</div>
<h2>Joint Tracking</h2>
<div id="joints"></div>
<h2>Log</h2>
<div id="log"></div>
<script>
const es=new EventSource('/events');
es.onmessage=e=>{
  const d=JSON.parse(e.data);
  const ml=d.mode==='VISIBLE'?'GOOD':
    d.mode==='FULL_OCCLUSION'||d.mode==='IMU_DISCONNECTED'?'ERROR':
    d.mode==='FUTON_MODE'?'INFO':'WARNING';
  const mc=d.mode==='VISIBLE'?'green':d.mode==='FULL_OCCLUSION'?'red':
    d.mode==='FUTON_MODE'?'cyan':'yellow';
  document.getElementById('mode').textContent=d.mode+' ('+ml+')';
  document.getElementById('mode').className='card-value '+mc;
  document.getElementById('fps').textContent=Math.round(d.fps||0);
  const confEl=document.getElementById('conf');
  confEl.innerHTML=Math.round((d.avg_conf||0)*100)+'<span class="card-unit">%</span>';
  const vt=d.visible_threshold||0.7,pt=d.partial_threshold||0.3;
  confEl.className='card-value '+(d.avg_conf>vt?'green':d.avg_conf>pt?'yellow':'red');
  const st=document.getElementById('status');
  st.textContent=ml;
  st.style.color=mc==='green'?'var(--green)':mc==='red'?'var(--red)':'var(--yellow)';
  st.style.setProperty('--dot',mc==='green'?'var(--green)':mc==='red'?'var(--red)':'var(--yellow)');
  if(st.querySelector('::before'))st.querySelector('::before').style.background=st.style.color;
  const jc=document.getElementById('joints');
  if(d.joints){
    jc.replaceChildren();
    for(const[name,j]of Object.entries(d.joints)){
      const c=j.conf>vt?'var(--green)':j.conf>pt?'var(--yellow)':'var(--red)';
      const cc=j.conf>vt?'green':j.conf>pt?'yellow':'red';
      const lbl=j.conf>vt?'GOOD':j.conf>pt?'WARN':'LOW';
      // Build via DOM API so joint 'name' (which may originate from
      // a BLE/serial device advertising an attacker-chosen string if
      // that path is ever wired in) cannot inject HTML/JS.
      const row=document.createElement('div');row.className='joint';
      const ns=document.createElement('span');ns.className='joint-name';ns.textContent=name;
      const bar=document.createElement('div');bar.className='bar';
      const fill=document.createElement('div');fill.className='bar-fill';
      fill.style.width=(j.conf*100)+'%';fill.style.background=c;
      bar.appendChild(fill);
      const cs=document.createElement('span');cs.className='joint-conf '+cc;
      cs.textContent=(j.conf*100).toFixed(0)+'% '+lbl;
      row.append(ns,bar,cs);jc.appendChild(row);
    }
  }
  const log=document.getElementById('log');
  const ts=new Date().toLocaleTimeString('ja-JP',{hour12:false});
  const line=document.createElement('div');
  const mode=document.createElement('span');mode.className='log-mode';mode.textContent=d.mode;
  const val=document.createElement('span');val.className='log-val';val.textContent=((d.avg_conf||0)*100).toFixed(0)+'%';
  line.append(ts+' ',mode,' conf=',val);
  log.appendChild(line);
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

    def update(
        self,
        mode: str,
        fps: float,
        avg_conf: float,
        joints: dict | None = None,
        visible_threshold: float = 0.7,
        partial_threshold: float = 0.3,
    ) -> None:
        with _lock:
            _latest_state.update({
                "mode": mode,
                "fps": round(fps, 1),
                "avg_conf": round(avg_conf, 3),
                "joints": joints or {},
                "visible_threshold": visible_threshold,
                "partial_threshold": partial_threshold,
            })

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server = None
