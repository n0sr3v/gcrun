---
title: "Fusion360 Path Setup"
tags: []
author: chatgpt
count: 5
exporter: 3.1.0
date: 2026-05-21T10-28-14+0200
url: https://chatgpt.com/c/6a0c0a8d-7afc-8384-8cd8-ecff02a68f4b
---

# Fusion360 Path Setup

## Table of Contents

- [1: i am in Fusion360 manufacture, how do i get the path for surrounding c…](#chat-1)
- [2: Check the images there is still only one path \(i have a 3D view not a…](#chat-2)
- [3: Okay here is the thing, there is not Post called "Marlin" by itsself,…](#chat-3)
- [4: can you do the edits?](#chat-4)
- [5: can you also generate me a short arc test cnc code? how to make sure t…](#chat-5)

## chat-1

> i am in Fusion360 manufacture, how do i get the path for surrounding cuts and inner rectangle cutouts? Right now only for the 3mm holes a path is generated.
> I have a 2mm flat mill (already selected)

## chat-2

> Check the images there is still only one path (i have a 3D view not a 2D view from top)

## chat-3

> Okay here is the thing, there is not Post called "Marlin" by itsself, the closest in my opinion would be FFF generic, because basically it is 3D printer hardware (i can not control the spindle only the x/y/z movement, i set the spindle speed manually by hand), with grbl i get something that seems workable now, do you think it needs adjustments?

Yes — **for Marlin/RAMPS I would not run this file unchanged**. The GRBL post is much closer than FFF Generic, but your uploaded `1001.nc` still contains several CNC/GRBL-style commands that are risky or wrong for Marlin.

The actual contour part looks good in principle: it has multiple Z levels / ramps, not just one full-depth plunge. The problems are mostly **header/footer and command compatibility**.

## Main problems in your `1001.nc`

### 1. Remove the `G28` lines

Your file contains:

```gcode
G28 G91 Z0
...
G28 G91 Z0
G28 G91 X0 Y0
```

On Marlin, `G28` means **home axes**, not “safe retract like on many CNC posts”. Marlin’s docs describe `G28` as auto-home for one or more axes. [Marlin Firmware](https://marlinfw.org/docs/gcode/G028.html)

For your CNC job, this can unexpectedly home Z/X/Y and crash or lose your manually touched-off work origin.

Replace this conceptually with normal moves, for example:

```gcode
G90
G0 Z16.5
G0 X0 Y0
```

Do **not** use `G28` inside the cutting file unless you really want to home the machine at that point.

In Fusion’s post options, look for something like:

```
Safe retracts: Clearance Height
```

instead of:

```
Safe retracts: G28
```

That is the cleanest fix.

### 2. Remove `M30`

Your file ends with:

```gcode
M5
M30
```

On normal CNC controls, `M30` often means program end. But in Marlin, `M30` is documented as **Delete SD file**. [Marlin Firmware](https://marlinfw.org/docs/gcode/M030.html)

So for Marlin: remove `M30`.

Use something harmless like:

```gcode
M400 ; wait for moves to finish
```

I would also **not** put `M84` at the end because your Z axis can fall when steppers disable.

### 3. Remove or avoid `T24`

Your file has:

```gcode
T24
```

For Marlin this is a tool/extruder select command. Tool `24` is very likely nonsense on your machine. Set the tool number in Fusion to something simple like `1`, but for Marlin CNC I would ideally remove the `T` line entirely.

In Fusion:

```
Tool Library → your 2 mm mill → Post Processor tab
Tool number: 1
```

### 4. Remove `S18000 M3` / `M5` if spindle is manual

Your file has:

```gcode
S18000 M3
...
M5
```

If your spindle is not electrically controlled, these commands are either ignored or could do something unintended if Marlin’s laser/spindle feature is enabled. Marlin documents `M3/M4/M5` as spindle/laser commands, so treat them as active commands, not just comments. [Marlin Firmware](https://marlinfw.org/docs/gcode/M030.html)

For manual spindle control, I would remove them and instead add a comment/pause manually, for example:

```gcode
; Start spindle manually before continuing
; M0 Start spindle manually
```

Only use `M0` if your Marlin setup handles pause/resume nicely.

### 5. `G54` may or may not work

Your file contains:

```gcode
G54
```

Marlin can support work coordinate systems such as `G54`, but only with the `CNC_COORDINATE_SYSTEMS` feature. Marlin’s docs list `G54-G59.3` as workspace coordinate systems. [Marlin Firmware](https://marlinfw.org/docs/gcode/G054-G059.html)

If your Marlin build is more “3D-printer-like”, `G54` may be unsupported. Safest for your current setup:

```gcode
; remove G54
```

Then manually set your origin before starting the file, for example with your controller UI or with `G92`, depending on how you normally touch off.

### 6. Important: your file uses `G18/G19` arcs

Your file contains lines like:

```gcode
G19 G3 ...
G18 G2 ...
```

These are arcs in non-XY planes, mostly from lead-in/lead-out/ramp transitions. Marlin’s `G2/G3` arc support depends on `ARC_SUPPORT`, and Marlin says `CNC_WORKSPACE_PLANES` allows `G2/G3` to operate in XY, ZX, or YZ planes. [Marlin Firmware](https://marlinfw.org/docs/gcode/G002-G003.html)

So this file requires Marlin to handle:

```
G17 XY plane
G18 ZX plane
G19 YZ plane
G2/G3 arcs
```

If your Marlin firmware does not have that enabled, the file may fail or move incorrectly.

Best Fusion-side fix:

```
Post options:
  Allow arcs / use G2-G3 arcs: disabled
```

or try to remove the small vertical arc leads:

```
2D Contour → Linking:
  Vertical Lead-In Radius: 0
  Vertical Lead-Out Radius: 0
```

If possible, make Fusion output only `G0` and `G1` linear moves. That is the safest for Marlin.

## The big Z-coordinate check

Your file says:

```gcode
(T24 D=2 CR=0 - ZMIN=1.4 - flat end mill)
```

And the cutting Z values go down to about:

```gcode
Z1.4
```

That means the file never goes negative in Z.

That is only correct if your physical machine zero matches Fusion’s setup origin exactly. If you plan to touch off the **top of the aluminium sheet as Z=0**, this file will not cut, because it never goes below zero.

For the usual CNC workflow with top-of-stock zero, I would expect something like:

```gcode
Z-0.2
Z-0.4
...
Z-1.55
```

For a 1.5 mm sheet, final Z should usually be around:

```
-1.55 mm
```

or maybe:

```
-1.60 mm
```

if you want to cut slightly into the spoilboard.

So before running it, decide clearly:

```
Fusion WCS origin = where you physically set X0 Y0 Z0 on the machine
```

If you want to touch off on the sheet top, fix the Fusion setup so the posted G-code has negative cutting Z values.

## Minimum manual cleanup for Marlin

At minimum, I would remove these lines from your current file:

```gcode
G28 G91 Z0
T24
S18000 M3
G54
...
G28 G91 Z0
G28 G91 X0 Y0
M5
M30
```

And use a simpler header/footer like:

```gcode
(1001 - Marlin manual spindle)
G21
G90
G17
G94
M17

; Make sure work origin is already set correctly before starting
; Start spindle manually before running cutting moves
```

End:

```gcode
M400
G90
G0 Z16.5
G0 X0 Y0
; Stop spindle manually
```

## My recommendation

Use the **GRBL post as a starting point**, but make it Marlin-safe by:

```
1. Safe retracts = Clearance Height, not G28
2. Disable/linearize arcs if your Marlin does not support G17/G18/G19 + G2/G3
3. Remove M30
4. Remove T24
5. Remove M3/M5 if spindle is manual
6. Confirm Z origin: top-zero should produce Z around -1.55 mm
```

After that, run an **air cut** first: spindle off, tool above the stock, and watch whether the XY motion and Z direction are correct.

___
###### [top](#table-of-contents)
## chat-4

> can you do the edits?

Done. I made two edited versions:

1. **Recommended for Marlin/RAMPS:**

Download `1001_marlin_linearized.nc`

This removes the unsafe CNC/GRBL commands and also converts `G2/G3` arcs into plain `G1` moves.

2. **Cleaner but still uses arcs:**

Download `1001_marlin_cleaned.nc`

This removes the unsafe commands but keeps `G2/G3`, `G18`, `G19` arcs. Only use this if your Marlin firmware supports arcs and CNC workspace planes reliably.

I changed:

```
Removed G28 homing moves
Removed G54
Removed T24
Removed S18000 M3 / M5
Removed M30
Removed G94
Added Marlin-style safe header
Added safe end move to Z16.5 and X0 Y0
Kept steppers enabled; no M84
```

Important: I **did not change the Z coordinate system**. Your file still cuts down to:

```
Z = 1.4 mm
```

It does **not** cut to negative Z. So only run this if your real machine/work origin matches the Fusion setup. If you intended to touch off the **top of the aluminium sheet as Z=0**, stop — this file still needs Z-origin correction.

I would test the `linearized` file first as an **air cut** with the spindle off and Z lifted safely above the material.

___
###### [top](#table-of-contents)
## chat-5

> can you also generate me a short arc test cnc code? how to make sure the general positioning is correct, i normally set the cnc mill on the bottom left corner (and want to make it start from here), in that position i can not move it any more to the left (-x) and not more to the lower (-y), meaning we are on the machine x=0 and y=0, as z high i usally set the point above the part (where the mill almost scratches the parts surface

Yes — here is a small **Marlin-safe XY arc test**:

Download `marlin_xy_arc_test.nc`

It does:

```
G92 X0 Y0 Z0   → treats current position as work zero
G0 Z5          → lifts 5 mm
XY moves only in positive X/Y
G3 arcs        → counter-clockwise arc test
G2 arcs        → clockwise arc test
No G28, no M30, no M84
```

The test stays at **Z=2 mm above the surface**, so it should be an air test and not cut.

### How to set up before running

Put the tool where you normally start:

```
X/Y: bottom-left corner of your intended work area
Z: almost touching the top surface
```

Then start the file. It will define that point as:

```
X0 Y0 Z0
```

and only move into positive X/Y, so it should not try to go left/down beyond your machine limit.

### What you should see

The machine should move like this:

```
1. Lift Z upward
2. Move slightly right/up into the work area
3. Draw a small rounded rectangle
4. Draw a small circle
5. Return to X0 Y0 with Z lifted
```

Maximum travel used:

```
X: 0 to 50 mm
Y: 0 to 30 mm
Z: 0 to +5 mm
```

### Important for the real cutting file

For your actual part, starting exactly at machine **X=0/Y=0** can be a problem if the outer contour needs to cut _outside_ the part. A 2 mm cutter needs radius clearance, so an outside contour may want to move to:

```
X = -1 mm
Y = -1 mm
```

That is impossible if you are already at the machine minimum.

Better workflow:

```
Home / go to machine minimum
Jog to X10 Y10 or similar
Place the material so the part origin is there
Set that point as work X0 Y0
```

Then your Fusion origin can still be the **bottom-left corner of the part**, but the machine has room for lead-ins, cutter radius, and outer contour moves.

___
###### [top](#table-of-contents)
