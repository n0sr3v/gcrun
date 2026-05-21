; Short air dry run from 1001_marlin_cleaned.nc
; Assumes current physical position is bottom-left of dry-run area and about 10 mm above the part.
; Set current position to X0 Y0 Z0 before running.
; Guarded streamer must reject any negative X/Y/Z command.

G21 ; units: mm
G90 ; absolute positioning
G17 ; XY plane
M17 ; enable steppers

G0 X66.65 Y37.9
Z16.5
G0 Z6.5
G1 Z4.2 F250
G19 G3 Y38.1 Z4 J0.2 K0 F500
G1 Y38.3
G17 G3 X66.45 Y38.5 I-0.2 J0

; First few contour passes only
G1 X51.2 Z3.988
Y8 Z3.963
X145.4 Z3.888
Y38.5 Z3.863
X51.2 Z3.788
Y8 Z3.763
X145.4 Z3.688
Y38.5 Z3.663

M400
