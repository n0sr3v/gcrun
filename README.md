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

## Fusion 360 G-code workflow
- In Manufacture, create a setup whose WCS origin matches the physical touch-off point. Bottom-left X/Y is safest because all X/Y moves are positive, but top-center/top-edge origins are supported when the job intentionally uses negative X/Y. For corrected top-surface-zero exports, touch the alloy surface and set the controller reference to `G92 X0 Y0 Z0`.
- Use a 2D Contour operation for the outside profile and rectangular cutouts. Use the 2 mm flat end mill, verify the stock/model orientation from top view, and simulate the job before posting.
- Prefer GRBL as the Fusion post if no Marlin post is available. FFF/3D-printer posts are not suitable for this CNC-style contour job.
- In the GRBL post options, use clearance-height retracts instead of `G28` if Fusion exposes that option. If possible, disable arcs or use linear output. If Fusion still emits arcs, the repo converter can linearize them.
- Do not rely on Fusion spindle commands for this machine. The spindle is controlled manually, so start/stop it by hand and let the G-code only control X/Y/Z.
- After posting from Fusion, upload/select the original `.nc` file in the web UI and click `Convert Fusion/GRBL to Marlin G0/G1`. Preview the converted file, dry-run the red outer extents at highest Z, then run only the converted file.
- The converter removes unsafe GRBL/Fusion commands for this Marlin setup: `G28`, `G54`/workspace selection, `T` tool select, `S... M3`, `M5`, `M30`, and plane switches. It linearizes `G2/G3` arcs in `G17/G18/G19` into explicit `G1` moves.
- Always check the converted Z range before cutting. Older `1001.nc` exported only positive cutting Z and expected the scratch surface to be represented as `Z4.2`. Newer corrected exports such as `1001_new.nc` cut below `Z0`, so they expect top-surface `Z0`.
- For top-center/top-edge jobs such as `1002.nc`, enable `Allow negative X/Y for center/top-edge origins` in the web UI before converting, previewing, dry-running, or running. Align the tool physically to the Fusion WCS point, then use `G92 X0 Y0 Z0` at the touched top surface.

## Direct rectangular cutouts
- See `DOGBONE_CUTOUTS.md` for the complete geometry, ramping, safety workflow, proven `41.9 x 42.4 mm` aluminium job, and GUI implementation specification.
- A rectangular inside cut needs cutter-radius compensation. Minimal 45-degree dogbones are separate out-and-back excursions from the compensated corners; they must not replace the straight wall path.
- Generate dry runs separately with no Z commands. Set the surface to `Z0` only after the user confirms the cutter is touching the stock top and is ready to cut.

## Project index
- `app.py` — Flask + pyserial CNC control UI. Provides jog controls, M114 position query, raw G-code send, and a full send/receive log.
- `requirements.txt` — Python dependencies for the web UI.
- `connect_check.py` — Termux/Android connection diagnostic helper for USB visibility, installed bridge apps, and open local TCP bridge ports.
- `normalize_marlin_gcode.py` — Converts Fusion/GRBL-style G-code into the explicit Marlin-compatible `G0/G1` format used by this machine, including arc linearization.
- `cnc_job.py` — Command-line G-code runner that validates files and streams one command at a time while waiting for Marlin `ok`.
- `DOGBONE_CUTOUTS.md` — Proven rectangular cutout workflow and parameterized GUI generator specification.
- `preperations/1001.nc` — Original Fusion 360 GRBL export used to build and verify the converter.
- `preperations/chatgpt_fusion360-path-setup_2026-05-21T10-28-14+0200.md` and `preperations/Fusion360 Path Setup_Tought_Process.pdf` — Earlier Fusion setup/conversion analysis notes.
- `1001_fusion_marlin_converted.nc` — Converter output generated from `preperations/1001.nc`.
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
- The web runner blocks files with unsupported arc/plane commands (`G2`, `G3`, `G17`, `G18`, `G19`) and bare modal axis/feed lines. It blocks negative X/Y by default for bottom-left jobs; enable the explicit negative-XY option only for jobs whose origin is intentionally centered or top-edge. Use `normalize_marlin_gcode.py` first for Fusion/Marlin compatibility.
- On Android/Termux, use `socket://127.0.0.1:2323` with USB Serial Telnet Server, or `socket://127.0.0.1:8888` with the included USB bridge, when direct serial devices are not exposed.
- Connection diagnostics: `python connect_check.py` checks visible serial nodes, `termux-usb`, installed bridge apps, and local TCP bridge ports. Use `python connect_check.py --command M115` after starting a bridge to ask Marlin for firmware info.
- Manual CNC run helper: `python cnc_job.py pos`, `python cnc_job.py lift 50`, `python cnc_job.py stop`, and `python cnc_job.py run 1001_marlin_linearized_marlin_zhop_start.nc --surface-z 4.2 --yes`. For top-center/top-edge jobs with negative X/Y, add `--allow-negative-xy` after verifying the extents. The runner validates files and streams one command at a time, waiting for Marlin `ok`.
- Scratch-point convention depends on the selected file. If the preview shows negative cutting Z, touch the alloy surface and set `G92 X0 Y0 Z0`. If the preview shows only positive cutting Z from the older job, use the older `G92 X0 Y0 Z4.2` convention.

## TODO
- None right now (add new tasks as needed).
