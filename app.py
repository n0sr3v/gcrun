import os
import re
import sys
import threading
import time
import json
import subprocess
from collections import deque

from flask import Flask, jsonify, render_template_string, request
import serial
if sys.platform == "android":
    list_ports = None
else:
    try:
        from serial.tools import list_ports
    except ImportError:
        list_ports = None


app = Flask(__name__)

DEFAULT_PORT = os.getenv("CNC_PORT", "COM13")
DEFAULT_BAUD = int(os.getenv("CNC_BAUD", "250000"))

LOG_LIMIT = 500
GCODE_EXTENSIONS = {".gcode", ".gc", ".nc", ".tap"}
MAX_PREVIEW_POINTS = 1200
AXIS_RE = re.compile(r"\b([XYZ])\s*(-?\d+(?:\.\d+)?)", re.IGNORECASE)
G_WORD_RE = re.compile(r"\bG(\d+(?:\.\d+)?)\b", re.IGNORECASE)
UNSUPPORTED_GCODE_RE = re.compile(r"\bG(17|18|19|2|3)\b", re.IGNORECASE)
BARE_MODAL_RE = re.compile(r"^[XYZEFIJK]", re.IGNORECASE)


class SerialManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._line_condition = threading.Condition(self._lock)
        self._ser = None
        self._reader = None
        self._running = False
        self._ok_count = 0
        self._error_count = 0
        self.log = deque(maxlen=LOG_LIMIT)
        self.position = {"x": None, "y": None, "z": None, "raw": None, "ts": None}

    def _append_log(self, direction, line):
        self.log.append(
            {
                "ts": time.strftime("%H:%M:%S"),
                "dir": direction,
                "line": strip_control_prefix(line).strip(),
            }
        )

    def _parse_position(self, line):
        line = strip_control_prefix(line)
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
                stripped = strip_control_prefix(line).strip().lower()
                if stripped == "ok" or stripped.startswith("ok "):
                    self._ok_count += 1
                    self._line_condition.notify_all()
                elif stripped.startswith("error") or stripped.startswith("echo:error"):
                    self._error_count += 1
                    self._line_condition.notify_all()

    def connect(self, port, baud):
        with self._lock:
            if self._ser and self._ser.is_open:
                return
            self._ser = serial.serial_for_url(port, baudrate=baud, timeout=0.5)
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

    def send_and_wait(self, line, timeout=300):
        line = line.strip()
        if not line:
            return
        with self._line_condition:
            if not self._ser or not self._ser.is_open:
                raise RuntimeError("Not connected")
            ok_before = self._ok_count
            error_before = self._error_count
            self._append_log("send", line)
            self._ser.write((line + "\n").encode())
            self._ser.flush()
            deadline = time.time() + timeout
            while True:
                if self._ok_count > ok_before:
                    return
                if self._error_count > error_before:
                    raise RuntimeError(f"Controller reported an error after: {line}")
                remaining = deadline - time.time()
                if remaining <= 0:
                    raise TimeoutError(f"Timed out waiting for ok after: {line}")
                self._line_condition.wait(remaining)

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


def strip_control_prefix(line):
    return re.sub(r"^[\x00-\x08\x0b\x0c\x0e-\x1f]+", "", line)


def clean_gcode_line(line):
    line = re.sub(r"\([^)]*\)", "", line)
    line = line.split(";", 1)[0].strip()
    return line


def list_gcode_files():
    files = []
    root = os.getcwd()
    for entry in os.scandir(root):
        if not entry.is_file():
            continue
        if os.path.splitext(entry.name)[1].lower() not in GCODE_EXTENSIONS:
            continue
        files.append(
            {
                "name": entry.name,
                "size": entry.stat().st_size,
            }
        )
    return sorted(files, key=lambda item: item["name"].lower())


def resolve_gcode_file(name):
    if not name or os.path.basename(name) != name:
        raise ValueError("Invalid G-code file name")
    if os.path.splitext(name)[1].lower() not in GCODE_EXTENSIONS:
        raise ValueError("Unsupported G-code file extension")
    path = os.path.abspath(os.path.join(os.getcwd(), name))
    root = os.path.abspath(os.getcwd())
    if os.path.dirname(path) != root:
        raise ValueError("G-code file must be in the repo root")
    if not os.path.isfile(path):
        raise FileNotFoundError(name)
    return path


def safe_upload_name(name):
    name = os.path.basename(name or "").strip()
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    if not name:
        raise ValueError("Missing file name")
    if os.path.splitext(name)[1].lower() not in GCODE_EXTENSIONS:
        raise ValueError("Unsupported G-code file extension")
    return name


def load_clean_gcode_lines(path):
    lines = []
    with open(path, "r", encoding="utf-8", errors="ignore") as handle:
        for raw_number, raw in enumerate(handle, start=1):
            line = clean_gcode_line(raw)
            if line:
                lines.append({"line": line, "raw_line": raw_number})
    return lines


def validate_marlin_job(lines):
    errors = []
    warnings = []
    for index, item in enumerate(lines, start=1):
        line = item["line"]
        raw_line = item["raw_line"]
        if UNSUPPORTED_GCODE_RE.search(line):
            errors.append(
                {
                    "line": raw_line,
                    "message": "Unsupported arc/plane command for this Marlin setup",
                    "text": line,
                }
            )
        if BARE_MODAL_RE.match(line):
            errors.append(
                {
                    "line": raw_line,
                    "message": "Bare modal axis/feed line; normalize to explicit G0/G1 first",
                    "text": line,
                }
            )
        axes = {axis.upper(): float(value) for axis, value in AXIS_RE.findall(line)}
        for axis, value in axes.items():
            if value < 0:
                errors.append(
                    {
                        "line": raw_line,
                        "message": f"Negative {axis} move is blocked for bottom-left work origin",
                        "text": line,
                    }
                )
        g_words = [word.upper() for word in G_WORD_RE.findall(line)]
        motion_words = {word for word in g_words if word in {"0", "00", "1", "01"}}
        if len(g_words) > 1 and motion_words:
            warnings.append(
                {
                    "line": raw_line,
                    "message": "Multiple G words on one line; verify firmware handles it as expected",
                    "text": line,
                }
            )
        if index >= 20 and len(errors) >= 20:
            errors.append({"line": None, "message": "Stopped validation after 20 errors", "text": ""})
            break
    return {"ok": not errors, "errors": errors, "warnings": warnings}


def analyze_gcode_file(name):
    path = resolve_gcode_file(name)
    lines = load_clean_gcode_lines(path)
    validation = validate_marlin_job(lines)
    pos = {"x": 0.0, "y": 0.0, "z": 0.0}
    ranges = {
        "x": {"min": None, "max": None},
        "y": {"min": None, "max": None},
        "z": {"min": None, "max": None},
    }
    points = []
    motion_count = 0
    for item in lines:
        line = item["line"]
        g_words = {word.upper() for word in G_WORD_RE.findall(line)}
        is_motion = bool(g_words.intersection({"0", "00", "1", "01"}))
        axes = {axis.lower(): float(value) for axis, value in AXIS_RE.findall(line)}
        if axes:
            for axis, value in axes.items():
                pos[axis] = value
                ranges[axis]["min"] = value if ranges[axis]["min"] is None else min(ranges[axis]["min"], value)
                ranges[axis]["max"] = value if ranges[axis]["max"] is None else max(ranges[axis]["max"], value)
            if is_motion and ("x" in axes or "y" in axes):
                motion_count += 1
                points.append({"x": pos["x"], "y": pos["y"], "z": pos["z"]})
    if len(points) > MAX_PREVIEW_POINTS:
        stride = max(1, len(points) // MAX_PREVIEW_POINTS)
        sampled = points[::stride]
        if sampled[-1] != points[-1]:
            sampled.append(points[-1])
        points = sampled
    highest_z = ranges["z"]["max"] if ranges["z"]["max"] is not None else 0.0
    outer = None
    if all(ranges[axis]["min"] is not None and ranges[axis]["max"] is not None for axis in ("x", "y")):
        outer = {
            "z": highest_z,
            "points": [
                {"x": ranges["x"]["min"], "y": ranges["y"]["min"]},
                {"x": ranges["x"]["max"], "y": ranges["y"]["min"]},
                {"x": ranges["x"]["max"], "y": ranges["y"]["max"]},
                {"x": ranges["x"]["min"], "y": ranges["y"]["max"]},
                {"x": ranges["x"]["min"], "y": ranges["y"]["min"]},
            ],
        }
    return {
        "file": os.path.basename(path),
        "size": os.path.getsize(path),
        "lines": len(lines),
        "motion_count": motion_count,
        "ranges": ranges,
        "highest_z": highest_z,
        "points": points,
        "outer": outer,
        "validation": validation,
    }


def build_outer_dry_run_lines(analysis, feed):
    outer = analysis.get("outer")
    if not outer:
        raise RuntimeError("Cannot build outer dry-run: file has no XY extents")
    z = outer["z"]
    points = outer["points"]
    lines = [
        "G21",
        "G90",
        f"G0 Z{z:.3f}",
        f"G0 X{points[0]['x']:.3f} Y{points[0]['y']:.3f}",
        f"G1 F{feed:.0f}",
    ]
    for point in points[1:]:
        lines.append(f"G1 X{point['x']:.3f} Y{point['y']:.3f}")
    lines.append("M400")
    return lines


class GCodeRunner:
    def __init__(self, serial_manager):
        self.manager = serial_manager
        self._lock = threading.Lock()
        self._thread = None
        self._cancel = threading.Event()
        self.status = {
            "running": False,
            "file": None,
            "sent": 0,
            "total": 0,
            "message": "Idle",
            "error": None,
        }

    def start(self, name, surface_z=None, set_origin=False, validate=True):
        path = resolve_gcode_file(name)
        with self._lock:
            if self.status["running"]:
                raise RuntimeError("A G-code job is already running")
            clean_items = load_clean_gcode_lines(path)
            if validate:
                validation = validate_marlin_job(clean_items)
                if not validation["ok"]:
                    first = validation["errors"][0]
                    raise RuntimeError(
                        f"File is not Marlin-compatible at line {first['line']}: {first['message']}"
                    )
            lines = [item["line"] for item in clean_items]
            if set_origin:
                if surface_z is None:
                    raise RuntimeError("Surface Z is required when setting the scratch origin")
                lines = ["G21", "G90", f"G92 X0 Y0 Z{surface_z:.3f}"] + lines
            if not lines:
                raise RuntimeError("No executable G-code lines found")
            self._cancel.clear()
            self.status = {
                "running": True,
                "file": os.path.basename(path),
                "sent": 0,
                "total": len(lines),
                "message": "Starting",
                "error": None,
            }
            self._thread = threading.Thread(
                target=self._run,
                args=(os.path.basename(path), lines),
                daemon=True,
            )
            self._thread.start()

    def start_lines(self, label, lines):
        clean = [line.strip() for line in lines if line and line.strip()]
        with self._lock:
            if self.status["running"]:
                raise RuntimeError("A G-code job is already running")
            if not clean:
                raise RuntimeError("No executable G-code lines found")
            self._cancel.clear()
            self.status = {
                "running": True,
                "file": label,
                "sent": 0,
                "total": len(clean),
                "message": "Starting",
                "error": None,
            }
            self._thread = threading.Thread(
                target=self._run,
                args=(label, clean),
                daemon=True,
            )
            self._thread.start()

    def cancel(self):
        self._cancel.set()
        with self._lock:
            if self.status["running"]:
                self.status["message"] = "Cancel requested"

    def snapshot(self):
        with self._lock:
            return dict(self.status)

    def _set_status(self, **kwargs):
        with self._lock:
            self.status.update(kwargs)

    def _run(self, filename, lines):
        try:
            for index, line in enumerate(lines, start=1):
                if self._cancel.is_set():
                    self._set_status(
                        running=False,
                        sent=index - 1,
                        message="Canceled",
                    )
                    return
                self._set_status(sent=index - 1, message=f"Sending line {index}/{len(lines)}")
                self.manager.send_and_wait(line)
                self._set_status(sent=index, message=f"Sent line {index}/{len(lines)}")
            self._set_status(running=False, sent=len(lines), message="Completed")
        except Exception as exc:
            self._set_status(running=False, message="Stopped on error", error=str(exc))


runner = GCodeRunner(manager)


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
        <select id="port" style="width: 150px;"></select>
        <input id="port-manual" type="text" placeholder="manual port" style="width: 120px;" />
        <button onclick="refreshPorts()">Refresh</button>
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
          <button onclick="autoHome()">Home</button>
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
          </div>
          <div class="row" style="margin-top: 6px;">
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
      <div class="row" style="margin-top: 10px;">
        <label class="muted">Move to</label>
        <input id="abs-x" type="number" step="0.1" placeholder="X" />
        <input id="abs-y" type="number" step="0.1" placeholder="Y" />
        <input id="abs-z" type="number" step="0.1" placeholder="Z" />
        <label class="muted">
          <input type="checkbox" id="abs-use-feed" />
          Use feed
        </label>
        <input id="abs-feed" type="number" step="1" value="1500" style="width: 100px;" />
        <button onclick="moveAbs()">Move</button>
      </div>
    </div>

    <div class="card">
      <div class="row">
        <strong>Run G-code file</strong>
        <select id="gcode-file" style="min-width: 220px;"></select>
        <input id="gcode-upload" type="file" accept=".gcode,.gc,.nc,.tap" />
        <button onclick="uploadGcodeFile()">Upload</button>
        <button onclick="refreshGcodeFiles()">Refresh files</button>
        <button onclick="loadGcodePreview()">Preview</button>
      </div>
      <div class="row" style="margin-top: 10px;">
        <button onclick="setBottomLeft()">Set bottom-left XY (G92 X0 Y0)</button>
        <label class="muted">Scratch surface Z</label>
        <input id="surface-z" type="number" step="0.01" value="4.2" style="width: 90px;" />
        <button onclick="setScratchPoint()">Set scratch point (G92 X0 Y0 Z)</button>
        <label class="muted">Outer dry feed</label>
        <input id="dry-feed" type="number" step="1" value="1500" style="width: 90px;" />
        <button onclick="dryRunOuter()">Dry-run outer extents at highest Z</button>
      </div>
      <div class="row" style="margin-top: 10px;">
        <label class="muted">
          <input type="checkbox" id="run-set-origin" checked />
          Set scratch origin before full run
        </label>
        <button onclick="runGcodeFile()">Run selected</button>
        <button onclick="cancelGcodeRun()">Cancel</button>
      </div>
      <div class="muted" style="margin-top: 8px;">
        Streams one validated line at a time and waits for Marlin <code>ok</code> before sending the next line. Full run assumes the selected file is already linearized/normalized for this Marlin setup.
      </div>
      <div class="canvas-wrap" style="margin-top: 12px;">
        <canvas id="gcode-preview" width="420" height="320" style="width:420px;height:320px;"></canvas>
        <div>
          <div class="muted">Preview: <span id="gcode-preview-status">No file preview loaded</span></div>
          <div class="muted" style="margin-top: 8px;">Extents: <span id="gcode-preview-extents">unknown</span></div>
          <div class="muted" style="margin-top: 8px;">Validation: <span id="gcode-validation">unknown</span></div>
        </div>
      </div>
      <div class="muted" style="margin-top: 8px;">
        Status: <span id="gcode-run-status">Idle</span>
      </div>
    </div>

    <div class="card">
      <div class="row">
        <strong>2D position + path</strong>
      </div>
      <div style="height: 12px;"></div>
      <div class="canvas-wrap">
        <canvas id="plot" width="420" height="320" style="width:420px;height:320px;"></canvas>
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
            <label class="muted">Z delta per run</label>
            <input id="path-zdelta" type="number" step="0.01" value="0" style="width: 90px;" />
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
      let gcodePreview = null;
      const storageKeys = {
        port: "cnc-port",
        baud: "cnc-baud",
        gcodeFile: "cnc-gcode-file",
        surfaceZ: "cnc-surface-z",
        dryFeed: "cnc-dry-feed",
        runSetOrigin: "cnc-run-set-origin",
        absX: "cnc-abs-x",
        absY: "cnc-abs-y",
        absZ: "cnc-abs-z",
        absUseFeed: "cnc-abs-use-feed",
        absFeed: "cnc-abs-feed"
      };

      function setStep(value) {
        step = value;
        document.getElementById("step-label").textContent = value;
      }

      async function connect() {
        const manualPort = document.getElementById("port-manual").value.trim();
        const portSelect = document.getElementById("port").value.trim();
        const port = manualPort || portSelect;
        const baud = document.getElementById("baud").value.trim();
        if (!port) {
          alert("Please select or enter a port.");
          return;
        }
        const res = await fetch("/connect", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ port, baud })
        });
        const data = await res.json();
        document.getElementById("status").textContent = data.status;
        if (res.ok) {
          localStorage.setItem(storageKeys.port, port);
          localStorage.setItem(storageKeys.baud, baud);
        }
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

      async function moveAbs() {
        const x = parseNumber("abs-x");
        const y = parseNumber("abs-y");
        const z = parseNumber("abs-z");
        if (x === null && y === null && z === null) return;
        const parts = [];
        if (x !== null) parts.push(`X${x.toFixed(3)}`);
        if (y !== null) parts.push(`Y${y.toFixed(3)}`);
        if (z !== null) parts.push(`Z${z.toFixed(3)}`);
        if (!parts.length) return;
        const useFeed = document.getElementById("abs-use-feed").checked;
        const feed = parseNumber("abs-feed");
        const lines = ["G90"];
        if (useFeed && feed) {
          lines.push(`G1 F${feed}`);
          lines.push(`G1 ${parts.join(" ")}`);
        } else {
          lines.push(`G0 ${parts.join(" ")}`);
        }
        await fetch("/send_batch", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ lines })
        });
        refreshLog();
        await queryPosition();
      }

      async function refreshGcodeFiles() {
        const select = document.getElementById("gcode-file");
        const stored = localStorage.getItem(storageKeys.gcodeFile);
        const res = await fetch("/gcode_files");
        const data = await res.json();
        const files = data.files || [];
        select.innerHTML = "";
        files.forEach(file => {
          const option = document.createElement("option");
          option.value = file.name;
          option.textContent = `${file.name} (${formatBytes(file.size)})`;
          select.appendChild(option);
        });
        if (stored && files.some(file => file.name === stored)) {
          select.value = stored;
        }
        select.onchange = () => {
          localStorage.setItem(storageKeys.gcodeFile, select.value);
          loadGcodePreview();
        };
        if (!files.length) {
          document.getElementById("gcode-run-status").textContent = "No .gcode/.nc/.tap files found in repo root";
        } else {
          loadGcodePreview();
        }
      }

      async function uploadGcodeFile() {
        const input = document.getElementById("gcode-upload");
        if (!input.files || !input.files.length) {
          alert("Choose a G-code file first.");
          return;
        }
        const form = new FormData();
        form.append("file", input.files[0]);
        const res = await fetch("/upload_gcode", { method: "POST", body: form });
        const data = await res.json();
        if (!res.ok) {
          alert(data.error || "Upload failed.");
          return;
        }
        localStorage.setItem(storageKeys.gcodeFile, data.file);
        await refreshGcodeFiles();
        document.getElementById("gcode-file").value = data.file;
        await loadGcodePreview();
      }

      async function loadGcodePreview() {
        const file = document.getElementById("gcode-file").value;
        const status = document.getElementById("gcode-preview-status");
        if (!file) {
          gcodePreview = null;
          status.textContent = "No file selected";
          drawGcodePreview();
          return;
        }
        localStorage.setItem(storageKeys.gcodeFile, file);
        const res = await fetch(`/gcode_preview?file=${encodeURIComponent(file)}`);
        const data = await res.json();
        if (!res.ok) {
          gcodePreview = null;
          status.textContent = data.error || "Preview failed";
          drawGcodePreview();
          return;
        }
        gcodePreview = data.preview;
        status.textContent = `${gcodePreview.file}, ${gcodePreview.lines} commands, ${gcodePreview.motion_count} XY moves`;
        document.getElementById("gcode-preview-extents").textContent = formatPreviewExtents(gcodePreview.ranges);
        const validation = gcodePreview.validation || {};
        if (validation.ok) {
          document.getElementById("gcode-validation").textContent = validation.warnings.length ? `OK with ${validation.warnings.length} warning(s)` : "OK";
        } else {
          const first = validation.errors && validation.errors[0];
          document.getElementById("gcode-validation").textContent = first ? `Blocked at line ${first.line}: ${first.message}` : "Blocked";
        }
        drawGcodePreview();
      }

      function formatPreviewExtents(ranges) {
        const fmt = axis => {
          const item = ranges[axis];
          if (!item || item.min === null || item.max === null) return `${axis.toUpperCase()}: unknown`;
          return `${axis.toUpperCase()}: ${item.min.toFixed(3)}..${item.max.toFixed(3)}`;
        };
        return [fmt("x"), fmt("y"), fmt("z")].join("  ");
      }

      async function setBottomLeft() {
        if (!confirm("Set current XY as work bottom-left with G92 X0 Y0?")) return;
        const res = await fetch("/work_origin/xy", { method: "POST" });
        const data = await res.json();
        if (!res.ok) alert(data.error || "Failed to set bottom-left XY.");
        refreshLog();
        await queryPosition();
      }

      async function setScratchPoint() {
        const surfaceZ = parseNumber("surface-z");
        if (surfaceZ === null) {
          alert("Enter the scratch surface Z value.");
          return;
        }
        if (!confirm(`Set current point as X0 Y0 Z${surfaceZ.toFixed(3)}?`)) return;
        const res = await fetch("/work_origin/scratch", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ surface_z: surfaceZ })
        });
        const data = await res.json();
        if (!res.ok) alert(data.error || "Failed to set scratch point.");
        refreshLog();
        await queryPosition();
      }

      async function dryRunOuter() {
        const file = document.getElementById("gcode-file").value;
        const feed = parseNumber("dry-feed") || 1500;
        if (!file) {
          alert("No G-code file selected.");
          return;
        }
        if (!confirm(`Dry-run the outer XY extents of ${file} at its highest Z?`)) return;
        const res = await fetch("/dry_run_outer", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ file, feed })
        });
        const data = await res.json();
        if (!res.ok) alert(data.error || "Failed to dry-run outer extents.");
        refreshGcodeStatus();
        refreshLog();
      }

      async function runGcodeFile() {
        const select = document.getElementById("gcode-file");
        const file = select.value;
        if (!file) {
          alert("No G-code file selected.");
          return;
        }
        if (!confirm(`Run ${file}? Make sure the tool, origin, clamps, and Z height are safe.`)) {
          return;
        }
        localStorage.setItem(storageKeys.gcodeFile, file);
        const surfaceZ = parseNumber("surface-z");
        const setOrigin = document.getElementById("run-set-origin").checked;
        const res = await fetch("/run_gcode", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ file, surface_z: surfaceZ, set_origin: setOrigin })
        });
        const data = await res.json();
        if (!res.ok) {
          alert(data.error || "Failed to start G-code run.");
        }
        refreshGcodeStatus();
      }

      async function cancelGcodeRun() {
        await fetch("/run_gcode/cancel", { method: "POST" });
        refreshGcodeStatus();
      }

      async function refreshGcodeStatus() {
        const res = await fetch("/run_gcode");
        const data = await res.json();
        const status = data.status || {};
        const parts = [];
        if (status.file) parts.push(status.file);
        parts.push(status.message || "Idle");
        if (status.total) parts.push(`${status.sent || 0}/${status.total}`);
        if (status.error) parts.push(`Error: ${status.error}`);
        document.getElementById("gcode-run-status").textContent = parts.join(" - ");
      }

      function formatBytes(bytes) {
        if (bytes < 1024) return `${bytes} B`;
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
        return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
      }

      function drawGcodePreview() {
        const canvas = document.getElementById("gcode-preview");
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
        ctx.fillStyle = "#fbfdff";
        ctx.fillRect(0, 0, width, height);
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
        if (!gcodePreview || !gcodePreview.ranges) return;
        const rx = gcodePreview.ranges.x;
        const ry = gcodePreview.ranges.y;
        if (rx.min === null || rx.max === null || ry.min === null || ry.max === null) return;
        const pad = 20;
        const spanX = Math.max(1, rx.max - rx.min);
        const spanY = Math.max(1, ry.max - ry.min);
        const scale = Math.min((width - pad * 2) / spanX, (height - pad * 2) / spanY);
        const mapX = x => pad + (x - rx.min) * scale;
        const mapY = y => height - pad - (y - ry.min) * scale;

        if (gcodePreview.outer && gcodePreview.outer.points) {
          ctx.strokeStyle = "#ef4444";
          ctx.setLineDash([8, 5]);
          ctx.lineWidth = 2;
          drawPreviewPolyline(ctx, gcodePreview.outer.points, mapX, mapY);
          ctx.setLineDash([]);
        }
        if (gcodePreview.points && gcodePreview.points.length > 1) {
          ctx.strokeStyle = "#1f6feb";
          ctx.lineWidth = 1.5;
          drawPreviewPolyline(ctx, gcodePreview.points, mapX, mapY);
        }
        ctx.fillStyle = "#111827";
        ctx.font = "12px Segoe UI";
        ctx.fillText("red = dry-run outer extents, blue = sampled XY toolpath", 12, height - 10);
      }

      function drawPreviewPolyline(ctx, points, mapX, mapY) {
        if (!points || points.length < 2) return;
        ctx.beginPath();
        ctx.moveTo(mapX(points[0].x), mapY(points[0].y));
        for (let i = 1; i < points.length; i++) {
          ctx.lineTo(mapX(points[i].x), mapY(points[i].y));
        }
        ctx.stroke();
      }

      function loadAbsMoveSettings() {
        const absX = localStorage.getItem(storageKeys.absX);
        const absY = localStorage.getItem(storageKeys.absY);
        const absZ = localStorage.getItem(storageKeys.absZ);
        const absFeed = localStorage.getItem(storageKeys.absFeed);
        const absUseFeed = localStorage.getItem(storageKeys.absUseFeed);
        if (absX !== null) document.getElementById("abs-x").value = absX;
        if (absY !== null) document.getElementById("abs-y").value = absY;
        if (absZ !== null) document.getElementById("abs-z").value = absZ;
        if (absFeed !== null) document.getElementById("abs-feed").value = absFeed;
        if (absUseFeed !== null) {
          document.getElementById("abs-use-feed").checked = absUseFeed === "true";
        }
      }

      function loadGcodeSettings() {
        const surfaceZ = localStorage.getItem(storageKeys.surfaceZ);
        const dryFeed = localStorage.getItem(storageKeys.dryFeed);
        const runSetOrigin = localStorage.getItem(storageKeys.runSetOrigin);
        if (surfaceZ !== null) document.getElementById("surface-z").value = surfaceZ;
        if (dryFeed !== null) document.getElementById("dry-feed").value = dryFeed;
        if (runSetOrigin !== null) {
          document.getElementById("run-set-origin").checked = runSetOrigin === "true";
        }
        document.getElementById("surface-z").addEventListener("input", event => {
          localStorage.setItem(storageKeys.surfaceZ, event.target.value);
        });
        document.getElementById("dry-feed").addEventListener("input", event => {
          localStorage.setItem(storageKeys.dryFeed, event.target.value);
        });
        document.getElementById("run-set-origin").addEventListener("change", event => {
          localStorage.setItem(storageKeys.runSetOrigin, event.target.checked);
        });
      }

      function bindAbsMovePersistence() {
        const fields = [
          ["abs-x", storageKeys.absX],
          ["abs-y", storageKeys.absY],
          ["abs-z", storageKeys.absZ],
          ["abs-feed", storageKeys.absFeed]
        ];
        fields.forEach(([id, key]) => {
          const el = document.getElementById(id);
          el.addEventListener("input", () => {
            localStorage.setItem(key, el.value);
          });
        });
        const useFeed = document.getElementById("abs-use-feed");
        useFeed.addEventListener("change", () => {
          localStorage.setItem(storageKeys.absUseFeed, useFeed.checked);
        });
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

      async function refreshPorts() {
        const select = document.getElementById("port");
        const stored = localStorage.getItem(storageKeys.port);
        const res = await fetch("/ports");
        const data = await res.json();
        const ports = data.ports || [];
        select.innerHTML = "";
        ports.forEach(port => {
          const option = document.createElement("option");
          option.value = port.device;
          option.textContent = port.description ? `${port.device} (${port.description})` : port.device;
          select.appendChild(option);
        });
        const existingValues = Array.from(select.options).map(opt => opt.value);
        const fallback = stored || "socket://127.0.0.1:2323";
        if (fallback && !existingValues.includes(fallback)) {
          document.getElementById("port-manual").value = fallback;
        } else {
          select.value = fallback;
        }
        select.onchange = () => {
          localStorage.setItem(storageKeys.port, select.value);
        };
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
        const zDelta = parseNumber("path-zdelta") || 0;
        const points = buildRectPathPoints(path.cx, path.cy, path.toolW, path.toolH);
        if (points.length < 2) return;
        const lines = [];
        lines.push("G90");
        if (document.getElementById("path-rapid").checked) {
          lines.push(`G0 X${points[0].x.toFixed(3)} Y${points[0].y.toFixed(3)}`);
        } else {
          lines.push(`G1 F${feed} X${points[0].x.toFixed(3)} Y${points[0].y.toFixed(3)}`);
        }
        if (Math.abs(zDelta) > 0) {
          const dz = zDelta / (points.length - 1);
          lines.push("G91");
          lines.push(`G1 F${feed}`);
          for (let i = 1; i < points.length; i++) {
            const dx = points[i].x - points[i - 1].x;
            const dy = points[i].y - points[i - 1].y;
            lines.push(`G1 X${dx.toFixed(3)} Y${dy.toFixed(3)} Z${dz.toFixed(3)}`);
          }
          lines.push("G90");
        } else {
          lines.push(`G1 F${feed}`);
          for (let i = 1; i < points.length; i++) {
            lines.push(`G1 X${points[i].x.toFixed(3)} Y${points[i].y.toFixed(3)}`);
          }
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
        setInterval(refreshGcodeStatus, 1000);
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
      refreshPorts();
      refreshGcodeFiles();
      loadAbsMoveSettings();
      loadGcodeSettings();
      bindAbsMovePersistence();
      const storedBaud = localStorage.getItem(storageKeys.baud);
      if (storedBaud) {
        const baudSelect = document.getElementById("baud");
        baudSelect.value = storedBaud;
      }
      document.getElementById("baud").addEventListener("change", event => {
        localStorage.setItem(storageKeys.baud, event.target.value);
      });
      refreshLog();
      refreshPosition();
      refreshGcodeStatus();
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


@app.get("/gcode_files")
def gcode_files():
    return jsonify({"files": list_gcode_files()})


@app.post("/upload_gcode")
def upload_gcode():
    uploaded = request.files.get("file")
    if not uploaded:
        return jsonify({"error": "Missing uploaded file"}), 400
    try:
        name = safe_upload_name(uploaded.filename)
        path = os.path.abspath(os.path.join(os.getcwd(), name))
        root = os.path.abspath(os.getcwd())
        if os.path.dirname(path) != root:
            raise ValueError("G-code file must stay in the repo root")
        uploaded.save(path)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True, "file": name, "files": list_gcode_files()})


@app.get("/gcode_preview")
def gcode_preview():
    name = request.args.get("file", "")
    try:
        preview = analyze_gcode_file(name)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"preview": preview})


@app.get("/run_gcode")
def run_gcode_status():
    return jsonify({"status": runner.snapshot()})


@app.post("/run_gcode")
def run_gcode():
    data = request.get_json(force=True)
    name = data.get("file", "")
    set_origin = bool(data.get("set_origin", False))
    surface_z = data.get("surface_z")
    if surface_z in ("", None):
        surface_z = None
    else:
        surface_z = float(surface_z)
    try:
        runner.start(name, surface_z=surface_z, set_origin=set_origin, validate=True)
    except Exception as exc:
        return jsonify({"error": str(exc), "status": runner.snapshot()}), 400
    return jsonify({"ok": True, "status": runner.snapshot()})


@app.post("/run_gcode/cancel")
def cancel_gcode():
    runner.cancel()
    return jsonify({"ok": True, "status": runner.snapshot()})


@app.post("/work_origin/xy")
def set_work_origin_xy():
    try:
        manager.send_and_wait("G92 X0 Y0")
        manager.send("M114")
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"ok": True})


@app.post("/work_origin/scratch")
def set_work_origin_scratch():
    data = request.get_json(force=True)
    try:
        surface_z = float(data.get("surface_z"))
        manager.send_and_wait(f"G92 X0 Y0 Z{surface_z:.3f}")
        manager.send("M114")
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"ok": True})


@app.post("/dry_run_outer")
def dry_run_outer():
    data = request.get_json(force=True)
    name = data.get("file", "")
    try:
        feed = float(data.get("feed") or 1500)
        analysis = analyze_gcode_file(name)
        validation = analysis["validation"]
        if not validation["ok"]:
            first = validation["errors"][0]
            raise RuntimeError(f"File is blocked at line {first['line']}: {first['message']}")
        lines = build_outer_dry_run_lines(analysis, feed)
        runner.start_lines(f"outer dry-run: {analysis['file']}", lines)
    except Exception as exc:
        return jsonify({"error": str(exc), "status": runner.snapshot()}), 400
    return jsonify({"ok": True, "status": runner.snapshot(), "lines": lines})


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

@app.get("/ports")
def ports():
    items = []

    # Add common TCP bridge ports
    items.append({"device": "socket://127.0.0.1:2323", "description": "USB Serial Telnet Server (2323)"})
    items.append({"device": "socket://127.0.0.1:8080", "description": "TCP Bridge (8080)"})
    items.append({"device": "socket://127.0.0.1:9000", "description": "TCP Bridge (9000)"})
    items.append({"device": "socket://127.0.0.1:8888", "description": "Termux Native Bridge"})

    if list_ports:
        try:
            for port in list_ports.comports():
                items.append(
                    {
                        "device": port.device,
                        "description": port.description,
                    }
                )
        except Exception as e:
            print(f"Error listing ports: {e}")

    # Add Termux USB ports if available
    if os.path.exists('/data/data/com.termux/files/usr/bin/termux-usb'):
        try:
            result = subprocess.run(['termux-usb', '-l'], capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                usb_devices = json.loads(result.stdout)
                for device_path in usb_devices:
                    if not any(p['device'] == device_path for p in items):
                        items.append({
                            "device": device_path,
                            "description": f"Termux USB: {device_path}"
                        })
        except Exception as e:
            print(f"Could not query Termux USB devices: {e}")

    return jsonify({"ports": items})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
