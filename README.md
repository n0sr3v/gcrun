# gcrun

Local CNC control and experiment repo for a Marlin + RAMPS 1.4 setup. This README is the index of everything currently in this project.

## Quick start (web UI)
- Install deps: `C:\Users\fn.local\AppData\Local\Programs\Python\Python311\python.exe -m pip install -r requirements.txt`
- Start server (background, logs to `server.log`): `run_server.cmd`
- Stop server (kills process listening on :5000): `stop_server.cmd`
- Open: `http://localhost:5000`

## Project index
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
- Default baud: `115200` (change in UI if needed, e.g. `250000`)
- If the UI shows garbled serial output, try another baud rate and reconnect.

## TODO
- Store last COM port and baud; provide a dropdown of available COM ports.
- Move Auto home (G28) into the X/Y/Z control area.
- Add a quick "Move to absolute position" UI next to the raw G-code send.
- Extend Play Path with an optional relative Z increment per run (default 0; positive/negative allowed).
