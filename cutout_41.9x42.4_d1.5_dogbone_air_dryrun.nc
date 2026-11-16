; XY-only air dry run for a finished 41.9 x 42.4 mm cutout.
; Origin: current tool position is the finished cutout top-left (X0 Y0).
; Direction: +X right, -Y down from the top edge.
; Cutter: 1.5 mm diameter (0.75 mm radius).
; Minimal 45-degree dogbone excursion: 0.31066 mm diagonally,
; giving 0.21967 mm relief beyond each finished wall.
; This file intentionally contains no Z commands.
G21
G90
M17
G92 X0 Y0
G1 F1500
; Move from the design corner to the compensated top-left corner.
G1 X0.75000 Y-0.75000
; Top-left dogbone.
G1 X0.53033 Y-0.53033
G1 X0.75000 Y-0.75000
; Top wall and top-right dogbone.
G1 X41.15000 Y-0.75000
G1 X41.36967 Y-0.53033
G1 X41.15000 Y-0.75000
; Right wall and bottom-right dogbone.
G1 X41.15000 Y-41.65000
G1 X41.36967 Y-41.86967
G1 X41.15000 Y-41.65000
; Bottom wall and bottom-left dogbone.
G1 X0.75000 Y-41.65000
G1 X0.53033 Y-41.86967
G1 X0.75000 Y-41.65000
; Left wall, repeat top-left relief, then return to the reference point.
G1 X0.75000 Y-0.75000
G1 X0.53033 Y-0.53033
G1 X0.75000 Y-0.75000
G1 X0 Y0
M400
