from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


SAMPLE_STATE = {
    "devices": [
        {
            "device_id": "control-usv-01",
            "device_type": "control_usv",
            "name": "Control USV 01",
            "lat": 35.052,
            "lon": 129.032,
            "state": "ready",
            "battery_pct": 94,
        },
        {
            "device_id": "auv-01",
            "device_type": "auv",
            "name": "AUV 01",
            "parent_device_id": "control-usv-01",
            "lat": 35.061,
            "lon": 129.039,
            "state": "surveying",
            "battery_pct": 87,
        },
        {
            "device_id": "rov-01",
            "device_type": "rov",
            "name": "ROV 01",
            "parent_device_id": "control-usv-01",
            "lat": 35.054,
            "lon": 129.034,
            "state": "standby",
            "battery_pct": 100,
        },
    ],
    "alerts": [
        {
            "alert_id": "alert-demo-001",
            "alert_type": "mine_detected",
            "severity": "warning",
            "device_ids": ["auv-01"],
            "message": "Mine-like sonar contact detected by auv-01",
        }
    ],
}


HTML = """<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>CoWater Dashboard PoC</title>
  <style>
    body { margin: 0; font-family: Arial, sans-serif; background: #0f172a; color: #e2e8f0; }
    header { padding: 16px 24px; border-bottom: 1px solid #334155; }
    main { display: grid; grid-template-columns: 1.2fr .8fr; gap: 16px; padding: 16px; }
    section { border: 1px solid #334155; border-radius: 6px; padding: 16px; background: #111827; }
    h1, h2 { margin: 0 0 12px; }
    .device, .alert { padding: 10px; border-bottom: 1px solid #1f2937; }
    .device:last-child, .alert:last-child { border-bottom: 0; }
    .map { height: 360px; position: relative; background: #082f49; overflow: hidden; border-radius: 4px; }
    .dot { position: absolute; width: 12px; height: 12px; border-radius: 50%; background: #38bdf8; transform: translate(-50%, -50%); }
    .dot.auv { background: #facc15; }
    .dot.rov { background: #fb7185; }
    small { color: #94a3b8; }
  </style>
</head>
<body>
  <header>
    <h1>CoWater Realtime Dashboard PoC</h1>
    <small>Mock API + live polling; no legacy frontend dependency</small>
  </header>
  <main>
    <section>
      <h2>Device Map</h2>
      <div class="map" id="map"></div>
    </section>
    <section>
      <h2>Devices</h2>
      <div id="devices"></div>
      <h2 style="margin-top:20px">Alerts</h2>
      <div id="alerts"></div>
    </section>
  </main>
  <script>
    async function refresh() {
      const state = await fetch('/api/state').then(r => r.json());
      const map = document.getElementById('map');
      map.innerHTML = '';
      for (const d of state.devices) {
        const dot = document.createElement('div');
        dot.className = 'dot ' + d.device_type;
        dot.title = d.name;
        dot.style.left = ((d.lon - 129.02) * 2500) + 'px';
        dot.style.top = (360 - ((d.lat - 35.04) * 9000)) + 'px';
        map.appendChild(dot);
      }
      document.getElementById('devices').innerHTML = state.devices.map(d =>
        `<div class="device"><b>${d.name}</b><br><small>${d.device_type} · ${d.state} · battery ${d.battery_pct}%</small></div>`
      ).join('');
      document.getElementById('alerts').innerHTML = state.alerts.map(a =>
        `<div class="alert"><b>${a.severity.toUpperCase()}</b> ${a.alert_type}<br><small>${a.message}</small></div>`
      ).join('');
    }
    refresh();
    setInterval(refresh, 1000);
  </script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send(200, "text/html", HTML.encode("utf-8"))
            return
        if parsed.path == "/api/state":
            state = mutate_state(SAMPLE_STATE)
            self._send(200, "application/json", json.dumps(state).encode("utf-8"))
            return
        self._send(404, "text/plain", b"not found")

    def log_message(self, format: str, *args) -> None:
        return

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def mutate_state(state: dict) -> dict:
    tick = int(time.time()) % 60
    data = json.loads(json.dumps(state))
    for idx, device in enumerate(data["devices"]):
        device["lat"] += (tick % 5) * 0.0002 * (idx + 1)
        device["lon"] += (tick % 7) * 0.0002 * (idx + 1)
    return data


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8744)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"dashboard poc listening on http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
