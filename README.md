# gcrun

Local CNC control and experiment repo for a Marlin + RAMPS 1.4 setup. This README is the index of everything currently in this project.

## Quick start (web UI)
- Install deps: `C:\Users\fn.local\AppData\Local\Programs\Python\Python311\python.exe -m pip install -r requirements.txt`
- Start server (background, logs to `server.log`): `run_server.cmd`
- Stop server (kills process listening on :5000): `stop_server.cmd`
- Open: `http://localhost:5000`

## Project index
- [isel-cnc session, 2026-11-17](cnc-session-2026-11-17.md) — German report covering the four contour cuts, tool change, USB/homing recovery, and two-point edge machining.
- `app.py` — Flask + pyserial CNC control UI. Provides jog controls, M114 position query, raw G-code send, and a full send/receive log.
- `requirements.txt` — Python dependencies for the web UI.
- `run_server.cmd` — Launches the Flask app in the background and redirects logs to `server.log`.
- `stop_server.cmd` — Stops the Flask app by killing the process listening on port 5000.
- `commit_msg.cmd` — Helper to commit with a message on Windows CMD without quoting issues.
- `gcode_script.md` — CNC session notes and manual workflow summary (feeds, depths, geometry, setup).
- `cnbstar_schuko.gcode` — Example G-code file for a specific job.
- `.gitignore` — Ignores `server.log`.
- `server.log` — Runtime log output from `app.py` (not tracked by Git).

## Notes
- Default serial port: `COM13`
- Default baud: `250000` (change in UI if needed)
- If the UI shows garbled serial output, try another baud rate and reconnect.
- Port list is loaded from the OS; last selected port + baud are stored locally.
- The absolute move row stores last-used X/Y/Z and feed settings.
- Play Path supports an optional Z delta per run (relative, interpolated across segments).

## TODO
- None right now (add new tasks as needed).
