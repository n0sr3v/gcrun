# gcrun

Local CNC control and experiment repo for a Marlin + RAMPS 1.4 setup. This README is the index of everything currently in this project.

## Quick start (web UI)
- Install deps: `C:\Users\fn.local\AppData\Local\Programs\Python\Python311\python.exe -m pip install -r requirements.txt`
- Start server (background, logs to `server.log`): `run_server.cmd`
- Stop server (kills process listening on :5000): `stop_server.cmd`
- Open: `http://localhost:5000`

## Android / Termux quick start
- Start the USB Serial Telnet Server bridge app on Android with the RAMPS/Marlin board connected through OTG.
- Use port `socket://127.0.0.1:2323` and baud `250000` in the web UI.
- If the bridge cannot see the board, check that Android OTG is enabled; on some devices it disables itself after a few minutes.
- Run `python connect_check.py --command M115` to verify the bridge can reach Marlin before moving the machine.

## Project index
- `app.py` — Flask + pyserial CNC control UI. Provides jog controls, M114 position query, raw G-code send, and a full send/receive log.
- `requirements.txt` — Python dependencies for the web UI.
- `connect_check.py` — Termux/Android connection diagnostic helper for USB visibility, installed bridge apps, and open local TCP bridge ports.
- `normalize_marlin_gcode.py` — Converts already-linearized G-code into the explicit Marlin-compatible format used by this machine.
- `cnc_job.py` — Command-line G-code runner that validates files and streams one command at a time while waiting for Marlin `ok`.
- `1001_marlin_linearized_marlin_zhop_start.nc` — Normalized full job with a safe initial Z-hop before XY travel.
- `1001_marlin_linearized_marlin.nc` — Normalized full job without the extra initial Z-hop.
- `1001_marlin_linearized_marlin_resume_from_line70.nc` — Resume variant from the earlier interrupted/manual run.
- `1001_marlin_cleaned.nc` and `1001_marlin_linearized.nc` — Intermediate source files kept for traceability; use the normalized `*_marlin*.nc` outputs for this Marlin setup.
- `1001_*_dryrun.nc` and `marlin_xy_arc_test*.nc` — Short dry-run/test files used to validate motion behavior without cutting the full job.
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
- Run G-code file lists `.gcode`, `.gc`, `.nc`, and `.tap` files in the repo root. It streams one cleaned line at a time and waits for Marlin `ok` before continuing.
- The G-code run card can upload/select a file, preview sampled XY toolpath plus red outer extents, set current XY as bottom-left (`G92 X0 Y0`), set the scratch/surface point (`G92 X0 Y0 Z...`), dry-run the outer extents at the file's highest Z, and run the validated file.
- The web runner blocks files with unsupported arc/plane commands (`G2`, `G3`, `G17`, `G18`, `G19`), bare modal axis/feed lines, or negative XYZ coordinates. Use `normalize_marlin_gcode.py` first for Fusion/Marlin compatibility.
- On Android/Termux, use `socket://127.0.0.1:2323` with USB Serial Telnet Server, or `socket://127.0.0.1:8888` with the included USB bridge, when direct serial devices are not exposed.
- Connection diagnostics: `python connect_check.py` checks visible serial nodes, `termux-usb`, installed bridge apps, and local TCP bridge ports. Use `python connect_check.py --command M115` after starting a bridge to ask Marlin for firmware info.
- Manual CNC run helper: `python cnc_job.py pos`, `python cnc_job.py lift 50`, `python cnc_job.py stop`, and `python cnc_job.py run 1001_marlin_linearized_marlin_zhop_start.nc --surface-z 4.2 --yes`. The runner validates files and streams one command at a time, waiting for Marlin `ok`.
- The proven scratch-point convention for this job is to touch the alloy surface at the bottom-left of the part, then set `G92 X0 Y0 Z4.2`. The file cuts below that reference down to about `Z1.4`; verify Z steps/mm before relying on depth.

## TODO
- None right now (add new tasks as needed).
