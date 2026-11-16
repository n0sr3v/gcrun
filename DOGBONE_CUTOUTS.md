# Rectangular Cutouts With Minimal Dogbone Corners

This document records the proven workflow for generating a rectangular inside
cutout directly for the Marlin CNC. It also defines the geometry and safety
logic needed to add a cutout generator to the Flask GUI.

## Proven Job

The first job using this logic was completed successfully on 2026-08-18:

- Finished opening: `41.9 x 42.4 mm`.
- Cutter: `1.5 mm` diameter flat end mill (`0.75 mm` radius).
- Material: approximately `2.0 mm` aluminium plate.
- Work origin: current tool position at the finished opening's top-left corner.
- Axis direction from that origin: `+X` to the right and `-Y` toward the bottom.
- Surface reference: tool scratching the top surface, then `G92 X0 Y0 Z0`.
- Cutting feed: `500 mm/min`.
- Final depth: `Z-2.4 mm`.
- Step-down: `0.2 mm` per complete contour, implemented as a continuous ramp.
- Passes: 12 ramp contours plus one constant-depth cleanup contour.
- Final retract: `Z5`, followed by return to `X0 Y0`.
- Connection: `socket://127.0.0.1:2323` at `250000` baud.
- Streaming: one command at a time, waiting for Marlin `ok`.
- Result: all 166 commands completed without a Marlin error in about 315 seconds.

The exact files are:

- `cutout_41.9x42.4_d1.5_dogbone_air_dryrun.nc`: XY-only air dry run.
- `cutout_41.9x42.4_d1.5_dogbone_cut_z-2.4.nc`: proven cutting file.

## Finished Size Versus Tool-Center Path

The requested width and height describe the finished opening, not the motion of
the cutter center. Let:

- `W` = finished opening width.
- `H` = finished opening height.
- `D` = cutter diameter.
- `r = D / 2` = cutter radius.

For an inside cut, the straight tool-center rectangle is inset by one radius
from every finished wall:

```text
tool-center width  = W - D
tool-center height = H - D
```

For the proven job:

```text
W = 41.9
H = 42.4
D = 1.5
r = 0.75

tool-center width  = 40.4 mm
tool-center height = 40.9 mm
```

With a top-left origin and `+X/-Y` orientation, the four normal compensated
corners are:

```text
A top-left     = (r,       -r)
B top-right    = (W - r,   -r)
C bottom-right = (W - r,  -(H - r))
D bottom-left  = (r,      -(H - r))
```

For the proven dimensions these are:

```text
A = ( 0.75000,  -0.75000)
B = (41.15000,  -0.75000)
C = (41.15000, -41.65000)
D = ( 0.75000, -41.65000)
```

Simply following this rectangle leaves an inside radius equal to the cutter
radius. A sharp rectangular component cannot fully occupy those corners.

## Minimal 45-Degree Dogbone Geometry

A minimal diagonal dogbone moves the cutter center toward each design corner
until the cutter circumference reaches that exact corner.

The cutter center must be one radius from the design corner. At 45 degrees, its
distance from each adjacent finished wall is:

```text
c = r / sqrt(2)
```

The relief beyond each finished wall is:

```text
wall relief = r - c
            = r * (1 - 1 / sqrt(2))
```

The diagonal excursion from the normal compensated corner is:

```text
diagonal excursion = sqrt(2 * r^2) - r
                   = r * (sqrt(2) - 1)
```

These two values are related but are not interchangeable. The diagonal
excursion is a distance along the 45-degree line. The wall relief is its X or Y
component.

For a `1.5 mm` cutter:

```text
r                  = 0.75000 mm
c                  = 0.53033 mm
wall relief        = 0.21967 mm
diagonal excursion = 0.31066 mm
```

The dogbone cutter-center points are therefore:

```text
P_top_left     = (c,       -c)
P_top_right    = (W - c,   -c)
P_bottom_right = (W - c,  -(H - c))
P_bottom_left  = (c,      -(H - c))
```

For the proven job:

```text
P_top_left     = ( 0.53033,  -0.53033)
P_top_right    = (41.36967,  -0.53033)
P_bottom_right = (41.36967, -41.86967)
P_bottom_left  = ( 0.53033, -41.86967)
```

Do not use `0.21967` as the dogbone point's distance from the design corner.
That number is only the relief beyond a wall. Doing so would produce an
unnecessarily large overcut.

## Correct Path Order

Dogbones are short out-and-back excursions from the normal compensated
corners. Moving only between the dogbone points would replace portions of the
straight walls with diagonal segments and change the opening geometry.

Starting at normal top-left point `A`, one complete contour is:

```text
A
P_top_left, A
B, P_top_right, B
C, P_bottom_right, C
D, P_bottom_left, D
A
```

This preserves all four straight finished walls while clearing every corner.
The initial move from work origin `(0, 0)` to `A` is through the material that
will become cutout waste.

## Continuous Z Ramping

For positive requested depth `depth` and positive maximum step-down `step`, use:

```text
pass_count = ceil(depth / step)
```

For pass `k`, where `k` starts at 1:

```text
start_depth = min((k - 1) * step, depth)
end_depth   = min(k * step, depth)
start_z     = -start_depth
end_z       = -end_depth
```

Let `L` be the total XY length of one complete contour, including dogbone
excursions, and `s` the cumulative XY distance at a path point. Interpolate Z
by path length:

```text
z(s) = start_z + (end_z - start_z) * (s / L)
```

This creates a gentle, consistent ramp and avoids a direct plunge. After the
last ramp reaches final depth, run one additional complete contour at constant
final Z so every wall and corner is cut to the same depth.

For `2.4 mm` depth and `0.2 mm` step-down:

```text
pass_count = ceil(2.4 / 0.2) = 12
```

The proven job descended by exactly `0.2 mm` over each contour and then made a
thirteenth cleanup contour at `Z-2.4`.

## Dry-Run Rules

The geometry dry run must be a separate generated file or command list:

- It must contain no `Z` words and no Z movement.
- It may set only `G92 X0 Y0` after the user confirms the current XY origin.
- It should trace the same compensated path and dogbone excursions as the cut.
- It should return to `X0 Y0` and finish with `M400`.
- It must use explicit `G0`/`G1`; do not emit arcs or bare modal lines.

Before the proven dry run, Marlin reported physical/work position
`X0 Y230 Z85`. The dry run preserved `Z85` and returned to `X0 Y0`.

## Cutting-File Rules

The cutting workflow requires an explicit user confirmation that:

- The current XY point is the intended finished top-left corner.
- The tool is touching or scratching the stock top surface.
- The spindle is running at the intended manual speed.
- The entire XY area, Z travel, clamps, cables, and spindle body are clear.

Only then set `G92 X0 Y0 Z0`. A typical generated file should:

```gcode
G21
G90
M17
G92 X0 Y0 Z0
G1 F500
; move through cutout waste to compensated contour at Z0
; ramp contours
; full-depth cleanup contour
M400
G0 Z5
G0 X0 Y0
M400
```

It must not contain `G28`, `M3`, `M4`, `M5`, `M30`, or `M84`. The spindle is
manual and the steppers must remain enabled to prevent Z sag.

## GUI Generator Specification

The GUI should expose these inputs:

- Finished width and height, in millimetres.
- Cutter diameter.
- Optional dimensional clearance, clearly defined as total or per side.
- Origin corner and axis orientation; initially support top-left with `+X/-Y`.
- Total cutting depth as a positive input, emitted as negative Z below surface.
- Maximum step-down per contour.
- XY cutting feed.
- Safe retract height above surface.
- Enable/disable minimal 45-degree dogbones.
- Enable/disable final cleanup contour, enabled by default.
- Dry-run mode, which must guarantee XY-only output.

The preview should draw distinct layers:

- Requested finished opening.
- Normal compensated tool-center path.
- Dogbone excursions.
- Cutter envelope or swept area, including relief outside the finished walls.
- Work origin and direction arrows.

Before generation, validate at least:

- `W > D` and `H > D`.
- Every numeric input is finite and positive where required.
- `step > 0`, `depth > 0`, `feed > 0`, and `safe_z > 0`.
- Calculated machine-coordinate ranges fit the available travel.
- A negative-axis warning is shown for top-left `+X/-Y` jobs.
- The final depth is not assumed from material thickness without user review.

The preview should report both centerline extents and swept cutter extents. For
the proven job:

```text
centerline X = 0.00000 .. 41.36967 (includes origin return)
centerline Y = -41.86967 .. 0.00000
cutting Z    = -2.40000 .. 0.00000
final safe Z = 5.00000
```

The swept cutter reaches the four requested walls and extends `0.21967 mm`
beyond each wall only near the dogbone corners.

## Fit, Tool, and Workholding Caveats

- An opening with the same nominal dimensions as a component is not guaranteed
  to fit. Account for cutter diameter error, spindle runout, machine backlash,
  material burrs, and the desired fit. Add deliberate clearance when needed.
- Use the measured effective cutter diameter when precision matters.
- Minimal dogbones mathematically clear an ideal sharp corner but provide no
  tolerance by themselves. Clearance remains a separate input.
- A through-cut frees the inner slug. It can shift, catch the cutter, or damage
  the finish. The GUI should warn about this and eventually support tabs or a
  deliberate final-breakthrough strategy.
- The plate may not be flat. Final depth needs enough margin to pass through the
  material, but excessive depth can cut the bed or fixture.
- Feed, step-down, and final depth are job-specific. The proven `F500`, `0.2 mm`,
  and `2.4 mm` values are evidence for this one aluminium job, not universal
  defaults for every cutter and material.
