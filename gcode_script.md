# CNC / Marlin / Pronterface Session Summary  
**Goal:** Create a repeatable, safe, manual-Z CNC workflow for cutting a rectangular **inside cutout** in **polycarbonate (PC)** using a **basic Marlin + RAMPS 1.4 CNC setup**, with **Pronterface** for control and **custom Python + serial GUI** planned next.

---

## 1. Machine & Control Context

### Hardware / Firmware
- CNC driven by **Marlin firmware** on **RAMPS 1.4**
- No automatic tool length probe
- Manual spindle speed control
- Manual Z stepping between passes
- Motion limits known:
  - **Y max = 230**
  - Z max ≈ 85
- Tool housing outer diameter: **70 mm**
- Cutting tool diameter: **6 mm**
- Cutter: **4-flute endmill** (usable but not ideal for plastics)

### Control Software
- **Pronterface** used for:
  - Jogging axes
  - Sending raw G-code
  - Manual zeroing via `G92`
- No CAM postprocessor in the loop
- Goal is **direct serial control from Python** in next step

---

## 2. Material & Cutting Constraints

### Material
- **Polycarbonate (PC)**
- Sheet thickness: **1.8 mm**
- PC is **heat-sensitive** → melts if chipload too small

### Cutter Geometry Notes
- **Flutes** = cutting edges
- **4-flute cutter**
  - Small chip space
  - Higher heat generation
  - Requires:
    - Lower RPM
    - Shallow depth per pass
    - Good chip evacuation

### Recommended Parameters (with 4-flute)
- Spindle RPM: **6,000 – 8,000**
- XY feed: **F1200 – F1500**
- Depth per pass: **0.15 – 0.30 mm**
- Total depth for through-cut: **~2.1 mm**
- Manual air blast / vacuum strongly recommended

---

## 3. Geometry to Be Cut

### Finished Cutout
- Rectangle (INSIDE cut / hole):
  - **Width:** 41.8 mm
  - **Height:** 42.3 mm

### Tool Compensation
- Tool diameter = **6.0 mm**
- Tool radius = **3.0 mm**

### Tool-Center Path Dimensions
| Dimension | Value |
|---------|------|
| Width   | 41.8 − 6 = **35.8 mm** |
| Height  | 42.3 − 6 = **36.3 mm** |

### Corner Result
- Inside corners have **3 mm radius** (tool-limited)

---

## 4. Coordinate Strategy (Critical)

### Alignment Requirements
- Rectangle is:
  - **Centered in X**
  - **Top-aligned to Y = 230**
- Y=230 is the **machine maximum** and must not be exceeded
- Tool housing (70 mm Ø) blocks visual center → manual compensation needed

---

## 5. Manual Positioning Workflow (One-Time Setup)

These steps are done **once** before running repeatable G-code loops.

### Step A – Absolute Mode
```gcode
G90
