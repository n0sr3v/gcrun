# Agent Knowledge: gcrun Marlin CNC on Android Termux

This repo controls a Marlin/RAMPS-style machine from Android Termux. Treat it as a real CNC machine with manual spindle control, not as a simulator. Prefer safe defaults, validate G-code before motion, and never send machine movement unless the user explicitly asks for it in the current session.

## Environment

- Working directory: `/data/data/com.termux/files/home/gcrun`.
- Runtime: Android Termux.
- Web UI: Flask app in `app.py`, served on `0.0.0.0:5000`.
- Primary connection path: USB Serial Telnet Server bridge on `socket://127.0.0.1:2323`.
- Baud rate: `250000`.
- Direct USB serial from Termux is not reliable here. Android blocks normal `/dev/ttyUSB*` or `/dev/ttyACM*` access, and `termux-usb` has previously failed with Android/linker issues.
- Android OTG may disable itself automatically after several minutes. If the bridge cannot see the machine, ask the user to re-enable OTG and restart the bridge server.
- The machine has a cheap display that can garble when the spindle runs at high RPM, likely due to EMI. Serial access may still work when the display is garbled, but query carefully and avoid unnecessary motion.

## Hardware / Machine Assumptions

- Marlin-based 3D-printer-style controller is being reused as a CNC motion controller.
- Manual spindle: the G-code must not depend on spindle start/stop commands. The user starts/stops RPM manually.
- Do not disable steppers at job end. Z can sag/drop if motors are disabled.
- The machine can be homed with `G28` only when the user explicitly says it is safe. Never include `G28` in normal cutting files.
- User often starts at the bottom-left of the workpiece. That position is also near machine minimum X/Y, so negative X/Y from the work origin is unsafe.
- For the proven `1001` job, work coordinates are non-negative:
  - `X`: `0.0 .. 189.4`
  - `Y`: `0.0 .. 46.55`
  - `Z`: `1.4 .. 16.5`
- Earlier proven touch-off convention for the first `1001` job: user touched/scratched the alloy surface at bottom-left, then set `G92 X0 Y0 Z4.2`.
- Newer Fusion exports may use the corrected CNC convention: physical top surface is `Z0`, cutting depths are negative, and scratch/touch-off should use `G92 X0 Y0 Z0`.
- Always inspect the selected file's Z range before setting the scratch reference. A file with negative cutting Z expects top-surface `Z0`; a file with only positive cutting Z may be using the older `Z4.2` surface convention.
- The user observed Z motion seemed strange, possibly due firmware steps/mm or mechanical calibration. Always surface Z-range and depth assumptions before cutting.

## Communication / Safety Rules

- Do not send motion commands unless the user explicitly requests machine movement in the current session.
- Before cutting or dry-running, state the file, coordinate ranges, origin convention, and whether the run is air/dry/cutting.
- Prefer one-command-at-a-time streaming with Marlin `ok` handshaking. Avoid queueing large batches into Marlin.
- `Cancel` in the web UI stops the sender, but Marlin may still drain already queued motion. Because this project now waits for `ok` per line, queue depth should be small, but do not assume instant physical stop.
- For emergency stop, `M410` may stop moves on Marlin builds that support it, but physical power-cycle may still be necessary.
- After power cycling the board, absolute/work positions are lost. Re-home if safe, then manually re-establish work origin.
- Never use `M84`/motor-off at the end of CNC files unless the user explicitly requests it and accepts Z sag risk.
- Avoid running the spindle from software (`M3`, `M4`, `M5`) because the spindle is manual and Marlin spindle/laser support could make those active unexpectedly.

## Bridge / Connection Workflow

Use the bridge, not direct USB:

```sh
python connect_check.py
python connect_check.py --command M115
```

Expected useful port in the UI:

```text
socket://127.0.0.1:2323
```

If connection fails:

- Confirm Android OTG is enabled.
- Confirm the USB Serial Telnet Server app has its server started.
- Confirm the bridge is set to `250000` baud.
- Use `python connect_check.py --ports 2323 --command M115`.
- If `termux-usb -l` fails or times out, that does not block the TCP bridge workflow.

## Important Files

- `app.py`: Flask web UI and serial/G-code runner.
- `normalize_marlin_gcode.py`: Fusion/GRBL-to-Marlin converter. It removes unsafe commands and linearizes arcs.
- `cnc_job.py`: CLI runner for probe/position/lift/stop/run. It validates and streams one command at a time.
- `connect_check.py`: Android/Termux connection diagnostics.
- `README.md`: User-facing workflow documentation.
- `preperations/1001.nc`: Original Fusion 360 GRBL export.
- `preperations/chatgpt_fusion360-path-setup_2026-05-21T10-28-14+0200.md`: Prior reasoning and Fusion setup notes.
- `preperations/Fusion360 Path Setup_Tought_Process.pdf`: Prior thought process dump for the conversion discussion.
- `1001_fusion_marlin_converted.nc`: Converted output generated from `preperations/1001.nc`.
- `1001_marlin_linearized_marlin_zhop_start.nc`: Previously normalized full job with explicit initial Z-hop.
- `1001_marlin_linearized_marlin.nc`: Normalized full job without extra first Z-hop.
- `1001_marlin_linearized_marlin_resume_from_line70.nc`: Resume variant used after an interrupted/manual run.
- `1001_arc_short_air_dryrun.nc`, `1001_linearized_short_air_dryrun.nc`, `marlin_xy_arc_test*.nc`: test/dry-run files used during machine bring-up.

One-off older USB experiments may remain untracked:

- `bridge_ftdi.py`, `ftdi_tcp_bridge.py`, `identify_usb.py`, `test_usb.py`, `check_fd*.py`, `run_bridge.sh`.
- Treat these as historical experiments unless the user asks to revisit native USB.

## Fusion 360 Workflow Knowledge

Goal: create contour/cutout paths in Fusion Manufacture and post something that can be converted to this Marlin machine.

Fusion setup:

- Manufacture workspace.
- Tool: 2 mm flat end mill.
- Operation: 2D Contour for surrounding cut and inner rectangular cutouts.
- Simulate in Fusion before posting.
- Set WCS/origin deliberately. For corrected top-surface-zero jobs, use bottom-left X/Y and top stock surface as `Z0`.
- If the physical workflow is changed to top-of-stock `Z0`, the Fusion setup and posted Z values must change; do not assume.

Post processor:

- Use GRBL as the starting post when no Marlin CNC post is available.
- FFF/generic 3D-printer post is not appropriate for this CNC contour job.
- Prefer post settings:
  - Safe retracts: clearance height, not `G28`.
  - Disable/use no arcs if possible.
  - If arcs remain, use the repo converter.

Known problematic GRBL/Fusion commands for Marlin:

- `G28 G91 Z0`, `G28 G91 X0 Y0`: unsafe homing/retract semantics on Marlin.
- `G54`: may require Marlin CNC coordinate system support; remove and use `G92` work origin.
- `T24`: invalid/nonsense tool select for this machine.
- `S18000 M3`, `M5`: spindle is manual; remove.
- `M30`: dangerous in Marlin context because Marlin documents `M30` as delete SD file, not just program end.
- `G17`, `G18`, `G19` plus `G2/G3`: this Marlin setup reported arc capability but rejected/failed required plane/arc behavior in practice. Convert to explicit `G1`.
- Bare modal lines like `X...`, `Y...`, `Z...`, `F...` without explicit `G0/G1`: reject or normalize to explicit motion commands.
- Negative X/Y values are blocked by the current validators because the work origin is bottom-left. Negative Z is allowed for corrected top-surface-zero Fusion jobs.

## Converter Behavior

`normalize_marlin_gcode.py` converts Fusion/GRBL-style files into Marlin-safe explicit `G0/G1`.

It should:

- Strip comments for parsing.
- Remove unsafe GRBL/Fusion commands: `G28`, `G54`/workspace selection, `T`, `S... M3`, `M5`, `M30`, plane-only switches.
- Track modal motion and absolute coordinates.
- Linearize `G2/G3` arcs in `G17`, `G18`, and `G19`.
- Emit `G21`, `G90`, `M17`, and an initial safe `G0 Z16.5` before first XY travel.
- Keep steppers enabled at the end.
- End with `M400`, `G90`, `G0 Z16.5`, `G0 X0 Y0`, `M400`.

Typical conversion:

```sh
python normalize_marlin_gcode.py preperations/1001.nc 1001_fusion_marlin_converted.nc
```

Useful options:

```sh
python normalize_marlin_gcode.py preperations/1001.nc output.nc --tolerance 0.05 --initial-z 16.5
```

After conversion, validate:

```sh
python cnc_job.py run 1001_fusion_marlin_converted.nc --dry-check
grep -nE '\b(G2|G3|G17|G18|G19|G28|G54|T[0-9]|M3|M4|M5|M30)\b' 1001_fusion_marlin_converted.nc
```

For `1001_fusion_marlin_converted.nc`, expected dry-check:

```text
commands: 1961
ranges: {'X': (0.0, 189.4), 'Y': (0.0, 46.55), 'Z': (1.4, 16.5)}
```

## Web UI Workflow

Start the app:

```sh
python app.py
```

Open:

```text
http://localhost:5000
```

Connection:

- Port: `socket://127.0.0.1:2323`
- Baud: `250000`

G-code workflow:

1. Upload/select original Fusion `.nc` or already converted `.nc`.
2. If original Fusion/GRBL export: click `Convert Fusion/GRBL to Marlin G0/G1`.
3. Preview the converted file. Blue path is sampled XY toolpath. Red path is outer extents/dry-run box, not a true extracted contour.
4. Move machine manually/jog to bottom-left touch-off point.
5. Set bottom-left XY with `G92 X0 Y0`, or set scratch point with the Z reference expected by the file. Use `G92 X0 Y0 Z0` for negative-Z top-surface-zero jobs; use `G92 X0 Y0 Z4.2` only for the older positive-Z job.
6. Use dry-run outer extents at highest Z before cutting.
7. Start spindle manually.
8. Run only validated converted/normalized files.

Current GUI conversion controls:

- Arc tolerance default: `0.05` mm.
- Initial safe Z default: `16.5` mm.
- Converted files are named like `<source>_marlin_g01.nc`, with numeric suffixes if needed.

## Backend Endpoints

Useful app endpoints:

- `GET /gcode_files`: list repo-root G-code files.
- `POST /upload_gcode`: upload a `.gcode`, `.gc`, `.nc`, or `.tap` file to repo root.
- `GET /gcode_preview?file=...`: parse extents, validation, sampled points, and outer dry-run box.
- `POST /convert_gcode`: convert selected Fusion/GRBL file to Marlin `G0/G1`.
- `POST /work_origin/xy`: send `G92 X0 Y0`.
- `POST /work_origin/scratch`: send `G92 X0 Y0 Z<surface_z>`.
- `POST /dry_run_outer`: stream generated outer extents box at highest file Z.
- `POST /run_gcode`: validate and run selected file one line at a time.
- `POST /run_gcode/cancel`: request sender cancellation.

## Validation Rules

The web runner and CLI validator should reject:

- `G2`, `G3`
- `G17`, `G18`, `G19`
- Bare modal axis/feed lines starting with `X`, `Y`, `Z`, `E`, `F`, `I`, `J`, or `K`
- Negative X/Y coordinates

The reason is not theoretical purity; it is based on this machine’s observed Marlin behavior. Marlin reported `Cap:ARCS:1`, but actual files containing plane switches/arcs and bare modal lines failed. Explicit `G0/G1` worked reliably.

## Proven Machine Session Notes

- TCP bridge at `127.0.0.1:2323` with `250000` baud worked.
- `M115` identified Marlin bugfix-2.1.x and reported `Cap:ARCS:1`.
- Despite reported arc support, the original/cleaned arc file was not compatible.
- Short linearized dry-run worked.
- Full job worked with normalized explicit `G0/G1` and one-command handshaking.
- The display garbled when spindle was manually spun up to around `18k RPM`; power cycling restored it, but grounding/shielding/EMI improvements are recommended.
- After controller power-cycle, work coordinates are lost. The prior workflow was: home axes if safe, move back to manually set bottom-left, touch/scratch surface, then set `G92 X0 Y0 Z4.2`.

## Verification Commands

Run these after code changes:

```sh
python -m py_compile app.py connect_check.py normalize_marlin_gcode.py cnc_job.py
python cnc_job.py run 1001_fusion_marlin_converted.nc --dry-check
python - <<'PY'
from app import app
client = app.test_client()
res = client.get('/gcode_preview', query_string={'file': '1001_fusion_marlin_converted.nc'})
print(res.status_code)
preview = res.get_json()['preview']
print(preview['validation']['ok'], preview['lines'], preview['motion_count'])
print(preview['ranges'])
PY
```

Do not call routes that send motion (`/work_origin/*`, `/dry_run_outer`, `/run_gcode`) as tests unless the user explicitly wants machine movement.

## Git / Repo Hygiene

- Logs and caches are ignored: `*.log`, `app.log`, `server.log`, `__pycache__/`.
- Do not commit runtime logs.
- Do not commit one-off USB debug scripts unless the user asks.
- Generated converted G-code can be committed when it is part of the documented/reproducible job.
- Preserve user changes in a dirty worktree; do not reset/revert unrelated files.
