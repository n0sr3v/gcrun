import os
import re
import threading
import time
from collections import deque

from flask import Flask, jsonify, render_template_string, request
import serial


app = Flask(__name__)

DEFAULT_PORT = os.getenv("CNC_PORT", "COM13")
DEFAULT_BAUD = int(os.getenv("CNC_BAUD", "115200"))

LOG_LIMIT = 500


class SerialManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._ser = None
        self._reader = None
        self._running = False
        self.log = deque(maxlen=LOG_LIMIT)
        self.position = {"x": None, "y": None, "z": None, "raw": None, "ts": None}

    def _append_log(self, direction, line):
        self.log.append(
            {
                "ts": time.strftime("%H:%M:%S"),
                "dir": direction,
                "line": line.strip(),
            }
        )

    def _parse_position(self, line):
        # Typical Marlin M114: "X:0.00 Y:0.00 Z:0.00 E:0.00 Count X:0 Y:0 Z:0"
        match = re.search(
            r"X:\s*(-?\d+\.?\d*)\s+Y:\s*(-?\d+\.?\d*)\s+Z:\s*(-?\d+\.?\d*)",
            line,
        )
        if not match:
            return
        self.position.update(
            {
                "x": float(match.group(1)),
                "y": float(match.group(2)),
                "z": float(match.group(3)),
                "raw": line.strip(),
                "ts": time.time(),
            }
        )

    def _read_loop(self):
        while self._running:
            try:
                line = self._ser.readline().decode(errors="ignore")
            except Exception:
                break
            if not line:
                continue
            with self._lock:
                self._append_log("recv", line)
                self._parse_position(line)

    def connect(self, port, baud):
        with self._lock:
            if self._ser and self._ser.is_open:
                return
            self._ser = serial.Serial(port, baudrate=baud, timeout=0.5)
            self._running = True
            self._reader = threading.Thread(target=self._read_loop, daemon=True)
            self._reader.start()
            self._append_log("status", f"Connected to {port} @ {baud}")

    def disconnect(self):
        with self._lock:
            if not self._ser:
                return
            self._running = False
            try:
                self._ser.close()
            finally:
                self._append_log("status", "Disconnected")
                self._ser = None

    def send(self, line):
        line = line.strip()
        if not line:
            return
        with self._lock:
            if not self._ser or not self._ser.is_open:
                raise RuntimeError("Not connected")
            self._append_log("send", line)
            payload = (line + "\n").encode()
            self._ser.write(payload)
            self._ser.flush()

    def is_connected(self):
        with self._lock:
            return bool(self._ser and self._ser.is_open)


manager = SerialManager()


INDEX_HTML = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>CNC Jog</title>
    <style>
      :root {
        color-scheme: light;
        font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
      }
      body {
        margin: 20px;
        background: #f4f7f9;
      }
      .grid {
        display: grid;
        grid-template-columns: repeat(3, minmax(80px, 1fr));
        gap: 8px;
        max-width: 280px;
      }
      button {
        padding: 10px 12px;
        border: 1px solid #d0d7de;
        border-radius: 8px;
        background: white;
        cursor: pointer;
      }
      button:hover {
        background: #eef3f7;
      }
      .row {
        display: flex;
        gap: 12px;
        align-items: center;
        flex-wrap: wrap;
      }
      .card {
        background: white;
        padding: 16px;
        border-radius: 12px;
        border: 1px solid #e3e8ee;
        margin-bottom: 16px;
      }
      textarea {
        width: 100%;
        min-height: 200px;
        font-family: Consolas, monospace;
        font-size: 12px;
      }
      input[type="text"] {
        padding: 8px;
        width: 260px;
      }
      .muted {
        color: #5b6b7a;
        font-size: 12px;
      }
    </style>
  </head>
  <body>
    <div class="card">
      <div class="row">
        <label class="muted">Port</label>
        <input id="port" type="text" value="COM13" />
        <label class="muted">Baud</label>
        <input id="baud" type="text" value="115200" />
        <button onclick="connect()">Connect</button>
        <button onclick="disconnect()">Disconnect</button>
        <span id="status" class="muted">Disconnected</span>
      </div>
    </div>

    <div class="card">
      <div class="row">
        <strong>Step:</strong>
        <button onclick="setStep(0.1)">0.1mm</button>
        <button onclick="setStep(1)">1mm</button>
        <button onclick="setStep(10)">10mm</button>
        <span class="muted">Current: <span id="step-label">1</span>mm</span>
      </div>
      <div style="height: 12px;"></div>
      <div class="row">
        <div>
          <div class="grid">
            <button onclick="jog('Y', step)">+Y</button>
            <button onclick="jog('Z', step)">+Z</button>
            <button onclick="jog('X', step)">+X</button>
            <button onclick="jog('Y', -step)">-Y</button>
            <button onclick="jog('Z', -step)">-Z</button>
            <button onclick="jog('X', -step)">-X</button>
          </div>
          <div class="muted" style="margin-top: 8px;">
            Jog uses G91 / G0 / G90 sequence.
          </div>
        </div>
        <div>
          <div class="row">
            <button onclick="queryPosition()">Query Position (M114)</button>
            <label class="muted">
              <input type="checkbox" id="auto-m114" onchange="toggleAutoM114()" />
              Auto M114
            </label>
          </div>
          <div class="muted" style="margin-top: 8px;">
            Position: <span id="position">unknown</span>
          </div>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="row">
        <input id="gcode-input" type="text" placeholder="G-code, e.g. G92 X0 Y0 Z0" />
        <button onclick="sendGcode()">Send</button>
      </div>
    </div>

    <div class="card">
      <div class="row">
        <strong>G-code log</strong>
        <button onclick="refreshLog()">Refresh</button>
      </div>
      <textarea id="log" readonly></textarea>
    </div>

    <script>
      let step = 1;
      let autoTimer = null;

      function setStep(value) {
        step = value;
        document.getElementById("step-label").textContent = value;
      }

      async function connect() {
        const port = document.getElementById("port").value.trim();
        const baud = document.getElementById("baud").value.trim();
        const res = await fetch("/connect", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ port, baud })
        });
        const data = await res.json();
        document.getElementById("status").textContent = data.status;
        refreshLog();
      }

      async function disconnect() {
        const res = await fetch("/disconnect", { method: "POST" });
        const data = await res.json();
        document.getElementById("status").textContent = data.status;
        refreshLog();
      }

      async function jog(axis, distance) {
        await fetch("/jog", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ axis, distance })
        });
        refreshLog();
      }

      async function sendGcode() {
        const input = document.getElementById("gcode-input");
        const line = input.value.trim();
        if (!line) return;
        await fetch("/send", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ line })
        });
        input.value = "";
        refreshLog();
      }

      async function refreshLog() {
        const res = await fetch("/log");
        const data = await res.json();
        const lines = data.log.map(entry => `[${entry.ts}] ${entry.dir}: ${entry.line}`);
        document.getElementById("log").value = lines.join("\\n");
      }

      async function queryPosition() {
        await fetch("/position", { method: "POST" });
        await refreshPosition();
      }

      async function refreshPosition() {
        const res = await fetch("/position");
        const data = await res.json();
        if (data.position && data.position.raw) {
          document.getElementById("position").textContent = data.position.raw;
        } else {
          document.getElementById("position").textContent = "unknown";
        }
      }

      function toggleAutoM114() {
        const checked = document.getElementById("auto-m114").checked;
        if (checked) {
          autoTimer = setInterval(queryPosition, 5000);
        } else if (autoTimer) {
          clearInterval(autoTimer);
          autoTimer = null;
        }
      }

      refreshLog();
      refreshPosition();
    </script>
  </body>
</html>
"""


@app.get("/")
def index():
    return render_template_string(INDEX_HTML)


@app.post("/connect")
def connect():
    port = request.json.get("port") if request.is_json else None
    baud = request.json.get("baud") if request.is_json else None
    port = port or DEFAULT_PORT
    baud = int(baud or DEFAULT_BAUD)
    try:
        manager.connect(port, baud)
    except Exception as exc:
        return jsonify({"status": f"Error: {exc}"}), 500
    return jsonify({"status": f"Connected ({port} @ {baud})"})


@app.post("/disconnect")
def disconnect():
    manager.disconnect()
    return jsonify({"status": "Disconnected"})


@app.post("/jog")
def jog():
    data = request.get_json(force=True)
    axis = data.get("axis", "").upper()
    distance = float(data.get("distance", 0))
    if axis not in {"X", "Y", "Z"} or distance == 0:
        return jsonify({"error": "Invalid jog command"}), 400
    try:
        manager.send("G91")
        manager.send(f"G0 {axis}{distance}")
        manager.send("G90")
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"ok": True})


@app.post("/send")
def send():
    data = request.get_json(force=True)
    line = data.get("line", "")
    try:
        manager.send(line)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"ok": True})


@app.get("/log")
def log():
    return jsonify({"log": list(manager.log)})


@app.get("/position")
def get_position():
    return jsonify({"position": manager.position})


@app.post("/position")
def request_position():
    try:
        manager.send("M114")
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"ok": True})


@app.get("/status")
def status():
    return jsonify({"connected": manager.is_connected()})


if __name__ == "__main__":
    # Enable auto-reload for local development.
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=True)
