# AV Ras2 — Architectural Decisions & Technical Log
**Artificial Vision, Inc.** | *Find your sense.*

This document details key architectural decisions, algorithms, and technical resolutions implemented during the development of AV Ras2.

---

## 1. Wall Poche vs. Stroke Intelligence (Milestone M4)

### The Core Problem
Most raster-to-vector tools treat all black pixels identically. For architectural floor plans where walls are rendered as solid black poche (filled regions), generic tracers generate either:
1. Jagged pixel outlines on both faces.
2. A single thin centerline losing wall thickness information.
3. A single thick polyline without editable boundary faces.

### The Architectural Decision
AV Ras2 deconstructs every solid filled region into two distinct geometric representations:
1. **Independent Boundary Lines (`A-WALL`)**:
   - The polygon of each wall cut is analyzed.
   - For rectilinear wall sections, the long parallel sides are extracted as two independent, continuous lines or polylines.
   - The end caps or jamb openings are isolated as distinct transverse lines.
   - Architects and CAD operators can trim, extend, offset, and snap to either wall face independently.
2. **Native CAD Hatch (`A-HATCH`)**:
   - A genuine native CAD `HATCH` entity (`SOLID` pattern) is generated enclosing the boundary loops (outer perimeter and internal voids/rooms).
   - In `ezdxf`, this is written as a native DXF Hatch with polyline boundary paths, recognized by AutoCAD, Revit, and BricsCAD.

---

## 2. Text & Dimension Intelligence (Resolution of Issue 1)

### The Problem
During testing of real Matterport exports (`Carroll-Residence.pdf`), room names (e.g. `PRIMARY BEDROOM`, `13'2" x 13'0"`) and labels were being converted into dozens of tiny line segments because the edge detector saw letter strokes as drawing lines.

### The Architectural Decision
1. **Intake Extraction**: PyMuPDF extracts native text strings, bounding boxes, and font sizes directly from the document.
2. **Text Masking Pipeline**:
   - Before executing distance transforms, Hough transforms, or contour detection, all text bounding box regions are filled with white background color on the binary geometry mask with a 3-pixel safety margin.
   - **Result**: Zero text characters are turned into line segments.
3. **Native CAD Text Generation**:
   - Text strings are converted into true CAD `TEXT` / `MTEXT` entities on `A-ANNO` (room names/labels) or `A-DIMS` (dimensions) with modelspace insertion points, rotation, and calibrated heights.

---

## 3. Manhattan Orthogonalization & Angle Rectification (Resolution of Issue 2)

### The Problem
Raster pixel staircasing and antialiasing along straight walls caused standard contour simplification (`approxPolyDP`) and Hough line transforms to produce slightly slanted line segments (e.g. 88.5° or 1.2°).

### The Architectural Decision
Implemented a strict **Orthogonal Rectification Engine**:
1. **Line Snapping**:
   - Segments within $\pm 5.5^\circ$ of 0° or 180° are snapped to **strict horizontal** ($y_1 = y_2 = \frac{y_1 + y_2}{2}$).
   - Segments within $\pm 5.5^\circ$ of 90° or 270° are snapped to **strict vertical** ($x_1 = x_2 = \frac{x_1 + x_2}{2}$).
   - Exactly identical coordinate values are assigned in CAD world space to eliminate floating point drift.
2. **Wall Polygon Rectification**:
   - Consecutive edge orientations of closed wall polygons are snapped to orthogonal axes.
   - Collinear intermediate vertices along straight spans are pruned, ensuring clean, continuous, non-fragmented wall runs.

---

## 4. Door Assembly Deconstruction & Swing Arc Fitting (Resolution of Issue 3)

### The Problem
Matterport exports draw door swings as piecewise-linear polyline chains (10 to 20 small line segments) touching the door leaf line and wall jamb. Generic tools either break the arc into 10 disjoint lines or fail circle fitting because the contour is connected to the leaf and wall.

### The Architectural Decision
1. **Contour Sub-Sequence Analysis**:
   - Rather than requiring the entire contour to be an isolated arc, AV Ras2 simplifies the connected door assembly and examines sub-sequences of vertices (windows of 4 to 14 points).
   - Radial deviation $\sigma_r / r$ and angular span $\Delta\theta$ are evaluated across the sub-sequence.
   - When a sequence satisfies $r \in [25, 250]$ px, $\sigma_r / r < 0.12$, and $\Delta\theta \in [68^\circ, 115^\circ]$, it is identified as a **door swing quadrant arc**.
2. **CAD Arc & Leaf Generation**:
   - Reconstructs one clean **`CADArc` on `A-DOOR`** and one straight **`CADLine` on `A-DOOR`** for the door leaf.
3. **Masking**:
   - Erases the detected door arc from the remaining thin-line pool so that Hough line transforms do not generate fragmented chord lines over the curved arc.

---

## 5. Scale Calibration & Coordinate System

### Coordinate Transform Math
Standard raster images use top-left origin ($+Y$ downwards), whereas CAD modelspace uses Cartesian coordinates ($+Y$ upwards).
AV Ras2 maintains dual coordinates:
$$\text{cad\_x} = (px - \text{origin\_x}) \times \text{units\_per\_pixel}$$
$$\text{cad\_y} = ((\text{image\_height} - py) - \text{origin\_y}) \times \text{units\_per\_pixel}$$

### Calibration Priority:
1. **Manual 2-Point Calibration**: User picks two reference points on the canvas and enters real-world distance.
2. **Matterport Scale Bar Detection**: Identifies alternating black/white scale bars with vertical tick marks in drawing margins.
3. **Room Dimension Text Calibration**: Matches dimension strings (e.g. `13'2" x 13'0"`) against room pixel extents to derive scale.
4. **Architectural Preset**: Fallback to standard scale ratios (e.g. 1/4" = 1'-0", 1/8" = 1'-0", 1:50, 1:100).
