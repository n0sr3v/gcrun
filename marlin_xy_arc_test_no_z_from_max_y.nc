(Marlin/RAMPS XY arc test - no Z motion, start at min X / max Y)
(Place tool at a safe height before running.)
(This file sets the current XY position as X0 Y0 and only moves in +X/-Y.)

G21            ; millimeters
G90            ; absolute positioning
G92 X0 Y0      ; define current XY position as work zero
M17            ; enable steppers

G0 X5 Y-5      ; move into positive X / negative Y work area

; CCW arc test mirrored for negative Y travel
G1 X30 Y-5 F600
G2 X35 Y-10 I0 J-5
G1 X35 Y-25
G2 X30 Y-30 I-5 J0
G1 X10 Y-30
G2 X5 Y-25 I0 J5
G1 X5 Y-10
G2 X10 Y-5 I5 J0

; CW arc test: small circle made from two semicircles
G0 X50 Y-20
G3 X40 Y-20 I-5 J0
G3 X50 Y-20 I5 J0

; Return in XY only
G0 X0 Y0
M400           ; wait for all moves to finish
