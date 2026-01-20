; Rectangle INSIDE test loop (XY only) - for manual Z stepping
; Finished cutout: 41.8 x 42.3 mm
; Tool: 6.0 mm (R=3.0)  => tool-center path: 35.8 x 36.3 mm
; Alignment: start at TOP-CENTER of finished rectangle at Y=230, centered in X
; This program returns to the exact start point so you can repeat after lowering Z manually.

G21 ; mm-mode
G90 ; absolute mode (for safety)
G91 ; incremental moves for the loop (so no need for G92 XY)

;G1 F1500 Y-3.0000        ; move from finished top edge to toolpath top edge (radius offset)

G1 F1500 X17.9000        ; to top-right of toolpath (35.8/2)
G1 F1500 Y-36.3000       ; down to bottom-right
G1 F1500 X-35.8000       ; left to bottom-left
G1 F1500 Y36.3000        ; up to top-left
G1 F1500 X35.8000        ; right to top-right
G1 F1500 X-17.9000       ; back to top-center of toolpath

;G1 F1500 Y3.0000         ; back to finished top edge line (original Y=230)
G90 ; restore absolute mode