import os
import re
import threading
import time
from collections import deque

from flask import Flask, jsonify, render_template_string, request
import serial


app = Flask(__name__)

DEFAULT_PORT = os.getenv("CNC_PORT", "COM13")
DEFAULT_BAUD = int(os.getenv("CNC_BAUD", "250000"))

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

    def send_many(self, lines):
        clean = [line.strip() for line in lines if line and line.strip()]
        if not clean:
            return
        with self._lock:
            if not self._ser or not self._ser.is_open:
                raise RuntimeError("Not connected")
            for line in clean:
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
      button, select, input, textarea {
        font-family: inherit;
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
      input[type="text"], input[type="number"], select {
        padding: 8px;
      }
      .muted {
        color: #5b6b7a;
        font-size: 12px;
      }
      .jog-layout {
        display: grid;
        grid-template-columns: repeat(3, 64px);
        grid-template-rows: repeat(3, 64px);
        gap: 6px;
        justify-content: center;
        align-items: center;
      }
      .jog-layout button {
        width: 64px;
        height: 64px;
      }
      .jog-z {
        display: flex;
        flex-direction: column;
        gap: 8px;
        margin-left: 16px;
      }
      .jog-wrap {
        display: flex;
        align-items: center;
        gap: 16px;
        flex-wrap: wrap;
      }
      .canvas-wrap {
        display: flex;
        gap: 16px;
        flex-wrap: wrap;
      }
      canvas {
        background: #fafcff;
        border: 1px solid #d6dde5;
        border-radius: 8px;
      }
      .field-group {
        display: grid;
        grid-template-columns: 140px 140px;
        gap: 8px;
        align-items: center;
      }
      .field-group label {
        font-size: 12px;
        color: #5b6b7a;
      }
      .field-group input {
        width: 120px;
      }
    </style>
  </head>
  <body>
    <div class="card">
      <div class="row">
        <label class="muted">Port</label>
        <input id="port" type="text" value="COM13" />
        <label class="muted">Baud</label>
        <select id="baud">
          <option value="250000" selected>250000</option>
          <option value="115200">115200</option>
          <option value="230400">230400</option>
          <option value="57600">57600</option>
          <option value="38400">38400</option>
          <option value="19200">19200</option>
          <option value="9600">9600</option>
        </select>
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
        <button onclick="setStep(100)">100mm</button>
        <span class="muted">Current: <span id="step-label">1</span>mm</span>
      </div>
      <div style="height: 12px;"></div>
      <div class="jog-wrap">
        <div class="jog-layout">
          <div></div>
          <button onclick="jog('Y', step)">Y+</button>
          <div></div>
          <button onclick="jog('X', -step)">X-</button>
          <div></div>
          <button onclick="jog('X', step)">X+</button>
          <div></div>
          <button onclick="jog('Y', -step)">Y-</button>
          <div></div>
        </div>
        <div class="jog-z">
          <button onclick="jog('Z', step)">Z+</button>
          <button onclick="jog('Z', -step)">Z-</button>
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
        <strong>2D position + path</strong>
      </div>
      <div style="height: 12px;"></div>
      <div class="canvas-wrap">
        <canvas id="plot" width="420" height="320"></canvas>
        <div>
          <div class="field-group">
            <label>Center X (mm)</label>
            <input id="path-cx" type="number" step="0.1" value="0" />
            <label>Center Y (mm)</label>
            <input id="path-cy" type="number" step="0.1" value="0" />
            <label>Width (mm)</label>
            <input id="path-w" type="number" step="0.1" value="41.8" />
            <label>Height (mm)</label>
            <input id="path-h" type="number" step="0.1" value="42.3" />
            <label>Tool Ø (mm)</label>
            <input id="path-d" type="number" step="0.1" value="6.0" />
            <label>Feed (mm/min)</label>
            <input id="path-f" type="number" step="1" value="1500" />
            <label>Limits Xmin</label>
            <input id="lim-xmin" type="number" step="1" value="" />
            <label>Limits Xmax</label>
            <input id="lim-xmax" type="number" step="1" value="" />
            <label>Limits Ymin</label>
            <input id="lim-ymin" type="number" step="1" value="" />
            <label>Limits Ymax</label>
            <input id="lim-ymax" type="number" step="1" value="" />
            <label>Use Y max as top</label>
            <input id="path-use-top" type="checkbox" checked />
          </div>
          <div style="height: 10px;"></div>
          <div class="row">
            <button onclick="autoHome()">Auto home (G28)</button>
            <button onclick="setCenterToCurrent()">Use current as center</button>
            <button onclick="addPath()">Add path</button>
            <button onclick="clearPath()">Remove path</button>
          </div>
          <div class="row" style="margin-top: 10px;">
            <button onclick="playPath()">Play path</button>
            <label class="muted">
              <input type="checkbox" id="path-rapid" checked />
              Rapid to start
            </label>
          </div>
          <div class="muted" style="margin-top: 8px;">
            Toolpath is width/height minus tool diameter, with rounded corners (r = tool Ø/2).
          </div>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="row">
        <strong>G-code log</strong>
      </div>
      <textarea id="log" readonly></textarea>
    </div>

    <script>
      let step = 1;
      let autoTimer = null;
      let logTimer = null;
      let positionTimer = null;
      let currentPos = { x: null, y: null, z: null };
      let path = null;

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
        await queryPosition();
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
        await queryPosition();
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
        await queryPosition();
      }

      async function refreshLog() {
        const res = await fetch("/log");
        const data = await res.json();
        const lines = data.log.map(entry => `[${entry.ts}] ${entry.dir}: ${entry.line}`);
        const textarea = document.getElementById("log");
        const nearBottom = textarea.scrollHeight - textarea.scrollTop - textarea.clientHeight < 30;
        textarea.value = lines.join("\\n");
        if (nearBottom) {
          textarea.scrollTop = textarea.scrollHeight;
        }
      }

      async function queryPosition() {
        await fetch("/position", { method: "POST" });
        await refreshPosition();
      }

      async function refreshPosition() {
        const res = await fetch("/position");
        const data = await res.json();
        if (data.position) {
          currentPos = {
            x: data.position.x,
            y: data.position.y,
            z: data.position.z
          };
          if (data.position.raw) {
            document.getElementById("position").textContent = data.position.raw;
          }
        } else {
          document.getElementById("position").textContent = "unknown";
        }
        drawPlot();
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

      function parseNumber(id) {
        const val = document.getElementById(id).value;
        const num = parseFloat(val);
        return Number.isFinite(num) ? num : null;
      }

      function setCenterToCurrent() {
        if (currentPos.x === null || currentPos.y === null) return;
        document.getElementById("path-cx").value = currentPos.x.toFixed(2);
        document.getElementById("path-cy").value = currentPos.y.toFixed(2);
      }

      function addPath() {
        const cx = parseNumber("path-cx");
        let cy = parseNumber("path-cy");
        const w = parseNumber("path-w");
        const h = parseNumber("path-h");
        const d = parseNumber("path-d");
        if (cx === null || w === null || h === null || d === null) return;
        const toolW = w - d;
        const toolH = h - d;
        const useTop = document.getElementById("path-use-top").checked;
        if (useTop) {
          if (currentPos.y === null) {
            alert("Position unknown. Click 'Query Position (M114)' first.");
            return;
          }
          cy = currentPos.y - toolH / 2;
          document.getElementById("path-cy").value = cy.toFixed(2);
        }
        if (cy === null) return;
        if (toolW <= 0 || toolH <= 0) {
          alert("Width/height must be larger than tool diameter.");
          return;
        }
        path = {
          cx,
          cy,
          w,
          h,
          d,
          toolW,
          toolH
        };
        drawPlot();
      }

      function clearPath() {
        path = null;
        drawPlot();
      }

      function buildRoundedPathPoints(cx, cy, w, h, r, segments) {
        const pts = [];
        const hw = w / 2;
        const hh = h / 2;
        const radius = Math.min(r, hw, hh);
        const addArc = (centerX, centerY, start, end) => {
          for (let i = 0; i <= segments; i++) {
            const t = start + (end - start) * (i / segments);
            pts.push({
              x: centerX + Math.cos(t) * radius,
              y: centerY + Math.sin(t) * radius
            });
          }
        };
        if (radius <= 0) {
          pts.push(
            { x: cx - hw, y: cy + hh },
            { x: cx + hw, y: cy + hh },
            { x: cx + hw, y: cy - hh },
            { x: cx - hw, y: cy - hh },
            { x: cx - hw, y: cy + hh }
          );
          return pts;
        }
        // Start at top edge, left to right, then clockwise.
        pts.push({ x: cx - hw + radius, y: cy + hh });
        pts.push({ x: cx + hw - radius, y: cy + hh });
        addArc(cx + hw - radius, cy + hh - radius, Math.PI / 2, 0);
        pts.push({ x: cx + hw, y: cy - hh + radius });
        addArc(cx + hw - radius, cy - hh + radius, 0, -Math.PI / 2);
        pts.push({ x: cx - hw + radius, y: cy - hh });
        addArc(cx - hw + radius, cy - hh + radius, -Math.PI / 2, -Math.PI);
        pts.push({ x: cx - hw, y: cy + hh - radius });
        addArc(cx - hw + radius, cy + hh - radius, -Math.PI, -1.5 * Math.PI);
        pts.push({ x: cx - hw + radius, y: cy + hh });
        return pts;
      }

      function buildRectPathPoints(cx, cy, w, h) {
        const hw = w / 2;
        const hh = h / 2;
        return [
          { x: cx, y: cy + hh },
          { x: cx + hw, y: cy + hh },
          { x: cx + hw, y: cy - hh },
          { x: cx - hw, y: cy - hh },
          { x: cx - hw, y: cy + hh },
          { x: cx, y: cy + hh }
        ];
      }

      async function playPath() {
        if (!path) return;
        const feed = parseNumber("path-f") || 1500;
        const points = buildRectPathPoints(path.cx, path.cy, path.toolW, path.toolH);
        if (points.length < 2) return;
        const lines = [];
        lines.push("G90");
        if (document.getElementById("path-rapid").checked) {
          lines.push(`G0 X${points[0].x.toFixed(3)} Y${points[0].y.toFixed(3)}`);
        } else {
          lines.push(`G1 F${feed} X${points[0].x.toFixed(3)} Y${points[0].y.toFixed(3)}`);
        }
        lines.push(`G1 F${feed}`);
        for (let i = 1; i < points.length; i++) {
          lines.push(`G1 X${points[i].x.toFixed(3)} Y${points[i].y.toFixed(3)}`);
        }
        await fetch("/send_batch", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ lines })
        });
        refreshLog();
        await queryPosition();
      }

      async function autoHome() {
        await fetch("/send", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ line: "G28" })
        });
        refreshLog();
        await queryPosition();
      }

      function updateCanvasSize() {
        const limXMin = parseNumber("lim-xmin");
        const limXMax = parseNumber("lim-xmax");
        const limYMin = parseNumber("lim-ymin");
        const limYMax = parseNumber("lim-ymax");
        const canvas = document.getElementById("plot");
        if (limXMin === null || limXMax === null || limYMin === null || limYMax === null) {
          return;
        }
        if (limXMax === limXMin || limYMax === limYMin) {
          return;
        }
        const width = 420;
        const ratio = Math.abs((limYMax - limYMin) / (limXMax - limXMin));
        const height = Math.max(240, Math.min(620, Math.round(width * ratio)));
        canvas.style.width = `${width}px`;
        canvas.style.height = `${height}px`;
      }

      function drawPlot() {
        const canvas = document.getElementById("plot");
        const ctx = canvas.getContext("2d");
        const dpr = window.devicePixelRatio || 1;
        const width = canvas.clientWidth || canvas.width;
        const height = canvas.clientHeight || canvas.height;
        const targetW = Math.round(width * dpr);
        const targetH = Math.round(height * dpr);
        if (canvas.width !== targetW || canvas.height !== targetH) {
          canvas.width = targetW;
          canvas.height = targetH;
        }
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.clearRect(0, 0, width, height);

        const limXMin = parseNumber("lim-xmin");
        const limXMax = parseNumber("lim-xmax");
        const limYMin = parseNumber("lim-ymin");
        const limYMax = parseNumber("lim-ymax");

        let xmin = limXMin;
        let xmax = limXMax;
        let ymin = limYMin;
        let ymax = limYMax;

        if (xmin === null || xmax === null || ymin === null || ymax === null || xmin === xmax || ymin === ymax) {
          const pad = 20;
          const focus = path ? {
            xmin: path.cx - path.w / 2 - pad,
            xmax: path.cx + path.w / 2 + pad,
            ymin: path.cy - path.h / 2 - pad,
            ymax: path.cy + path.h / 2 + pad
          } : null;
          if (focus) {
            xmin = focus.xmin;
            xmax = focus.xmax;
            ymin = focus.ymin;
            ymax = focus.ymax;
          } else if (currentPos.x !== null && currentPos.y !== null) {
            xmin = currentPos.x - 50;
            xmax = currentPos.x + 50;
            ymin = currentPos.y - 50;
            ymax = currentPos.y + 50;
          } else {
            xmin = 0;
            xmax = 200;
            ymin = 0;
            ymax = 200;
          }
        }

        const scaleX = width / (xmax - xmin);
        const scaleY = height / (ymax - ymin);

        const mapX = x => (x - xmin) * scaleX;
        const mapY = y => height - (y - ymin) * scaleY;

        ctx.strokeStyle = "#e1e8f0";
        ctx.lineWidth = 1;
        for (let i = 0; i <= 10; i++) {
          const x = (width / 10) * i;
          const y = (height / 10) * i;
          ctx.beginPath();
          ctx.moveTo(x, 0);
          ctx.lineTo(x, height);
          ctx.stroke();
          ctx.beginPath();
          ctx.moveTo(0, y);
          ctx.lineTo(width, y);
          ctx.stroke();
        }

        if (path) {
          const drawPolyline = (points) => {
            if (!points || points.length < 2) return;
            ctx.beginPath();
            ctx.moveTo(mapX(points[0].x), mapY(points[0].y));
            for (let i = 1; i < points.length; i++) {
              ctx.lineTo(mapX(points[i].x), mapY(points[i].y));
            }
            ctx.stroke();
          };

          // Finished rectangle (nominal cutout).
          ctx.strokeStyle = "#94a3b8";
          ctx.lineWidth = 1;
          ctx.setLineDash([6, 4]);
          drawPolyline(buildRectPathPoints(path.cx, path.cy, path.w, path.h));
          ctx.setLineDash([]);

          // Tool center path (rounded corners).
          ctx.strokeStyle = "#1f6feb";
          ctx.lineWidth = 2;
          const r = path.d / 2;
          drawPolyline(buildRoundedPathPoints(path.cx, path.cy, path.toolW, path.toolH, r, 12));
        }

        if (currentPos.x !== null && currentPos.y !== null) {
          ctx.fillStyle = "#e63946";
          ctx.beginPath();
          ctx.arc(mapX(currentPos.x), mapY(currentPos.y), 5, 0, Math.PI * 2);
          ctx.fill();
        }
      }

      function startAutoRefresh() {
        if (!logTimer) {
          logTimer = setInterval(refreshLog, 1000);
        }
        if (!positionTimer) {
          positionTimer = setInterval(refreshPosition, 2000);
        }
      }

      function saveLimits() {
        const fields = ["lim-xmin", "lim-xmax", "lim-ymin", "lim-ymax"];
        fields.forEach(id => {
          const val = document.getElementById(id).value;
          localStorage.setItem(id, val);
        });
        updateCanvasSize();
        drawPlot();
      }

      function loadLimits() {
        const fields = ["lim-xmin", "lim-xmax", "lim-ymin", "lim-ymax"];
        fields.forEach(id => {
          const stored = localStorage.getItem(id);
          if (stored !== null) {
            document.getElementById(id).value = stored;
          }
        });
        updateCanvasSize();
      }

      ["lim-xmin", "lim-xmax", "lim-ymin", "lim-ymax"].forEach(id => {
        document.addEventListener("input", event => {
          if (event.target && event.target.id === id) {
            saveLimits();
          }
        });
      });

      loadLimits();
      refreshLog();
      refreshPosition();
      startAutoRefresh();
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


@app.post("/send_batch")
def send_batch():
    data = request.get_json(force=True)
    lines = data.get("lines", [])
    try:
        manager.send_many(lines)
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
