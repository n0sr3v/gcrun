---
title: "Fusion360 Path Setup"
tags: []
author: chatgpt
count: 3
exporter: 3.1.0
date: 2026-05-21T13-49-53+0200
url: https://chatgpt.com/c/6a0c0a8d-7afc-8384-8cd8-ecff02a68f4b
---

# Fusion360 Path Setup

## Table of Contents

- [1: I am trying to add multiple pockets with adaptive clearing is it possi…](#chat-1)
- [2: Where/how should i set my Work Coordinate system Origin? I noticed rig…](#chat-2)
- [3: Ah got it i was confused about the preset ramp clearance hight \(that w…](#chat-3)

## chat-1

> I am trying to add multiple pockets with adaptive clearing is it possible to do them all with one "step", right now only one pocket is done although there are several selected?

Yes, **2D Adaptive can do multiple pockets in one operation**. Your screenshot already shows several entries under **Pocket Selections**, so selection is partly correct. If Fusion still only machines one pocket, usually one of these things is wrong:

## 1. Use the **bottom edge / bottom face** of each opening

For through-cut pockets in a 1.5 mm sheet, select the **bottom contour** of every cutout, not the top edge.

In **2D Adaptive → Geometry**:

1. Click **Pocket Selections**

2. Select the **bottom inside edge** of each rectangle/opening

3. Make sure each selected pocket turns pink

4. Check that all appear in the list as `Pockets 1`, `Pockets 2`, etc.

If you select top contours while your **Bottom Height** references selected geometry, Fusion can get confused or only calculate one usable region.

## 2. Check the **Heights** tab

For sheet material I would set:

```
Top Height: Model top / Stock top
Bottom Height: Model bottom
Bottom Offset: -0.05 to -0.10 mm
```

Do not use a bottom height that is tied to only one selected pocket.

## 3. Disable restrictions while testing

In your screenshot:

```
Rest Machining: off
Stock Contours: off
```

That is good.

Also check in the **Passes** tab whether anything like “machine shallow areas only” or “minimum cutting radius” is excluding pockets. For a 2 mm tool, small rectangles must be wide enough for the tool plus ramp/entry movement.

## 4. Entry/ramp can prevent some pockets

Adaptive needs an entry move. If the smaller pockets do not have enough room for the selected helix/ramp, Fusion may skip them.

Go to **Linking** or **Ramp** settings and try:

```
Ramp Type: Plunge
Ramp Clearance Height: small
Maximum Ramp Stepdown: 0.2 mm
```

or for aluminium better:

```
Ramp Type: Profile
Ramp Angle: 1–3°
Maximum Ramp Stepdown: 0.2 mm
```

But if a pocket is very small, **Profile Ramp** may fail because there is not enough path length. For testing, temporarily disable fancy leads/ramp or use simple plunge above scrap.

## 5. Regenerate the operation

After changing selection/settings:

```
Right-click 2D Adaptive operation → Generate
```

If it still only generates one region, right-click the operation and check whether Fusion gives a warning. The warning often says something like “empty toolpath” or “some pockets could not be machined.”

## 6. Practical recommendation for your part

For this thin 1.5 mm sheet, I would only use **2D Adaptive** for the larger cutouts if you want to clear material. For most of these openings, **2D Contour with multiple depths** is simpler and faster.

Good structure:

```
1. Drill holes
2. 2D Contour / Adaptive for inner cutouts
3. Outer 2D Contour last, with tabs
```

For small rectangular cutouts, adaptive clearing may be overkill. A 2 mm cutter following the inside contour in multiple 0.2 mm passes is usually enough.

So yes: **one 2D Adaptive operation can contain multiple pockets**, but if Fusion machines only one, check **bottom contour selection**, **Heights**, and **ramp/entry feasibility** first.

___
###### [top](#table-of-contents)
Yes, your assumption is basically correct: **selecting the lower edge is usually the safer choice for 2D Contour**, especially for through-cuts in sheet material.

But the exact reason is important:

## Edge selection defines two things

In Fusion 360, the contour edge selection gives Fusion:

1. the **XY contour shape**

2. often also the **Z reference**, depending on your **Heights** settings

So if you select the **upper edge** and your **Bottom Height** is somehow based on the selected contour, Fusion may think the cut target is at the top surface. Result: it generates a path above/on top of the part and does not actually cut through.

For through-cuts, select this:

```
Inner rectangular cutouts: lower inside edge
Outer contour: lower outside edge
```

That usually makes Fusion understand: “this contour goes all the way down to the bottom of the part.”

## For your 1.5 mm aluminium sheet

In the 2D Contour operation, use:

```
Geometry:
  Select lower edge of each cutout/perimeter

Heights:
  Top Height: Stock top / Model top
  Bottom Height: Selected contour / Model bottom
  Bottom Offset: -0.05 to -0.10 mm
```

So the final depth is slightly below the sheet, for example:

```
Final cut depth: 1.5 mm material + 0.05 mm = 1.55 mm total
```

## Important: your physical Z-zero must match Fusion

You said you set Z where the mill almost scratches the part surface. That means your real machine workflow is:

```
Z0 = top of aluminium sheet
```

In that case, your final G-code should usually contain negative Z values:

```gcode
Z-0.2
Z-0.4
Z-0.6
...
Z-1.55
```

If the generated G-code contains only positive cutting values like:

```gcode
Z1.4
```

then Fusion’s setup origin is probably not matching your real touch-off method. That would explain the “cutting in air” behavior.

## So for your workflow, check this

In **Setup → Setup tab / WCS**:

Your Fusion origin should be at:

```
X/Y: bottom-left of the part or stock
Z: top surface of the stock
```

Not the bottom of the model.

Then in the 2D Contour:

```
Select lower edges
Bottom Height: Model bottom or selected lower contour
Bottom Offset: -0.05 to -0.10 mm
```

After posting, check the G-code. For top-surface Z-zero, you want to see:

```gcode
G0 Z5
G1 Z-0.2
...
G1 Z-1.55
```

## Upper edge can work, but only if Heights are explicit

Selecting the upper edge is not always wrong. It can work if you explicitly set:

```
Bottom Height: Model bottom
Bottom Offset: -0.05 mm
```

But for avoiding mistakes, especially with thin sheet parts, I would use the rule:

```
For through-cut contours, select the lower edge.
```

Then simulate and verify the tool actually goes through the stock before exporting.

___
###### [top](#table-of-contents)
## chat-2

> Where/how should i set my Work Coordinate system Origin?
> 
> I noticed right now there are red paths and blue paths (the re path are above the part and the blue paths sink into the part?

You should set the **Fusion WCS origin exactly where you physically set X0/Y0/Z0 on the CNC**.

Since your normal workflow is:

```
X/Y = bottom-left corner of the part/work area
Z = tool just touching the top surface
```

then your Fusion setup should use:

```
WCS origin = top, bottom-left corner of the stock/workpiece
Z zero = top surface of aluminium
```

## Where to set it in Fusion 360

In Manufacture:

1. Right-click your **Setup4**

2. Click **Edit**

3. Go to the **Setup** tab

4. Under **Work Coordinate System**, set:

```
Orientation: Model orientation, if Z points up correctly
Origin: Stock box point
```

Then select the **top bottom-left corner** of the stock box.

The little WCS triad should sit on the top surface, not underneath the part.

You want something like:

```
Z blue arrow: upward, away from the part
X red arrow: to the right
Y green arrow: into/along the part
Origin: top-left/bottom-left corner where you touch off
```

The exact “bottom-left” depends on your screen view, but the important rule is:

```
From your chosen origin, the whole job should mostly move in positive X and positive Y.
```

## Very important: do not use the machine hard limit as work zero

You said at that position you cannot move further left or lower. That means you are at the machine’s physical `X0/Y0` limit.

That is risky, because an outside contour with a 2 mm cutter may need to move outside the model by 1 mm:

```
Tool radius = 1 mm
Outer contour may need X = -1 mm or Y = -1 mm
```

If the machine is already at its hard minimum, it cannot do that.

Better workflow:

```
1. Home the machine / move to machine lower-left
2. Jog to X10 Y10 or similar
3. Put your workpiece origin there
4. Touch Z on the top surface
5. Set this point as work X0 Y0 Z0
```

So machine coordinate might be:

```
Machine: X10 Y10
Work:    X0  Y0
```

Then if Fusion wants to move to `X-1`, the real machine only moves to machine `X9`, which is still possible.

## For your sheet part

I would set it like this:

```
Fusion Setup:
  WCS origin: top of stock, lower-left corner
  Z zero: top of aluminium sheet
  Stock thickness: 1.5 mm
  Bottom cut depth: about -1.55 mm
```

Then your posted G-code should contain cutting depths like:

```gcode
Z-0.2
Z-0.4
Z-0.6
...
Z-1.55
```

If your G-code has cutting depths like:

```gcode
Z1.4
```

while you touched off the top surface as `Z0`, then the WCS/Z origin is wrong and the machine will cut in air.

## About the red and blue paths

In Fusion, the colors are mostly **move types**, not simply “good” or “bad”.

Usually:

```
Blue paths = cutting/feed moves
Red/orange/yellow paths = linking, lead-in, ramp, plunge, or rapid moves
```

So a red path above the part is not automatically a problem. It may just be a travel or lead-in move. But if the **blue cutting path** is also above the part, then your Heights/WCS are wrong.

The real check is:

1. Right-click operation

2. **Simulate**

3. Enable stock visibility

4. Watch from the side

5. Check whether the tool actually enters the material and cuts through

Also check the posted G-code. For your workflow, final cutting Z should be negative, around:

```
Z-1.55 mm
```

## My recommended origin for you

Use this:

```
Fusion WCS origin:
  top surface of the stock
  lower-left corner of stock/workpiece

Physical CNC:
  jog to that same point
  tool just touching aluminium top
  set G92 X0 Y0 Z0 / Set Origin
```

But place that physical point **at least 5–10 mm away from the machine’s hard X/Y minimum**, so the cutter has room for outside contours and lead-ins.

___
###### [top](#table-of-contents)
## chat-3

> Ah got it i was confused about the preset ramp clearance hight (that was set to 2.5mm by default, meaning it would move alang the contour, ramping down from 2.5mm ahead of the part), can we lower this to speed up the manufacturing time? (when reducing this value, the red circling ramp down path above the tool reduces as well): What is confusing is that the red path start above the part based on the described offset and goes completely to the bottom whereas there is another blue path that is only within the part

Yes, you can lower **Ramp Clearance Height** to speed it up. For your case, **2.5 mm is unnecessarily high** if the sheet is flat and there are no clamps in the toolpath area.

For a **1.5 mm aluminium sheet**, I would try:

```
Ramp Clearance Height: 0.2–0.5 mm
```

A reasonable first value:

```
0.3 mm
```

That means the tool starts the ramp only 0.3 mm above the stock surface, instead of wasting time spiraling down from 2.5 mm above the part.

## Important distinction

There are several different “height” concepts:

```
Clearance / Retract height:
  Used for safe travel moves between features.
  Keep this high enough to clear clamps/screws/tabs.

Ramp Clearance Height:
  Only controls where the ramp-entry starts above the material.
  This can be much lower.
```

So I would not globally reduce all safe heights too much. But **Ramp Clearance Height** can definitely be reduced.

## Why red path above the part goes all the way down

That red spiral/circle/ramp is the **entry move**. It is Fusion’s way of avoiding a straight vertical plunge.

So instead of:

```
Move above pocket
Plunge straight down
Start cutting
```

it does:

```
Move above pocket
Circle/spiral/profile-ramp downward
Reach cutting depth
Continue with blue cutting path
```

The red path is therefore not necessarily “wrong”. It is the ramping entry path. Part of it is in air, part of it enters the material, and it can go down to the current cutting depth.

The **blue path** is the actual adaptive clearing / contour cutting path at the cutting depth.

## What I would set for your machine

For 1.5 mm aluminium, 2 mm end mill:

```
Ramp Clearance Height: 0.3 mm
Maximum Roughing Stepdown: 0.2 mm
Ramp Angle: 1–3°
Safe / Retract height: 1–3 mm, depending on clamps
```

If the sheet is taped/glued down and there are no clamps above the surface, you can use:

```
Safe/Retract height: 1.0 mm
Ramp Clearance Height: 0.2–0.3 mm
```

If there are clamps/screws nearby, keep safe/retract higher.

## Watch out for one thing

If the red ramp goes from above the part **directly all the way to final depth**, that can still be okay **only if the ramp angle is shallow enough**. But if it looks like a nearly vertical corkscrew/plunge, reduce aggressiveness:

```
Ramp Angle: 1–2°
Maximum Ramp Stepdown: 0.2 mm
```

For your setup, I would avoid a steep ramp. Aluminium and a weak CNC do not like aggressive plunging.

## Simple rule

Use:

```
Ramp Clearance Height: 0.3 mm
```

but keep a separate safe travel height high enough that the tool never hits clamps, screws, tabs, or curled sheet edges.

___
###### [top](#table-of-contents)

