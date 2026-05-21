(Marlin/RAMPS XY arc test - safe air run)
(Place tool at lower-left corner of the intended work area, almost touching the surface.)
(This file sets the current position as X0 Y0 Z0 and only moves in +X/+Y and +Z.)

G21            ; millimeters
G90            ; absolute positioning
G92 X0 Y0 Z0   ; define current position as work zero
M17            ; enable steppers

G0 Z5          ; lift 5 mm above surface
G0 X5 Y5       ; move into positive work area
G1 Z2 F120     ; stay 2 mm above surface for safe air test

; CCW arc test: rounded rectangle, all in positive X/Y
G1 X30 Y5 F600
G3 X35 Y10 I0 J5
G1 X35 Y25
G3 X30 Y30 I-5 J0
G1 X10 Y30
G3 X5 Y25 I0 J-5
G1 X5 Y10
G3 X10 Y5 I5 J0

; CW arc test: small circle made from two semicircles
G0 Z5
G0 X50 Y20
G1 Z2 F120
G2 X40 Y20 I-5 J0
G2 X50 Y20 I5 J0

; Return safely
G0 Z5
G0 X0 Y0
M400           ; wait for all moves to finish
; no M30, no M84, no G28
