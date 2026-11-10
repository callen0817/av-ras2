# AV Ras2 — Raster-to-CAD Reconstruction
**Artificial Vision, Inc.** | *Find your sense.*  
Website: [https://artificialviz.com](https://artificialviz.com)

AV Ras2 is a standalone, local-first engineering application designed to convert locked raster floor plans—specifically Matterport exports, schematic floor plans, and flattened architectural PDFs—into clean, scaled, and fully editable vector CAD geometry (`.dxf`, `.svg`, `.pdf`).

---

## The Core Technical Differentiator

Traditional raster-to-vector tracing tools generate thousands of tiny, disconnected pixel-edge segments that result in uneditable, fragile CAD linework.

**AV Ras2 performs geometry-aware architectural reconstruction:**
- **Thick Line vs. Wall Hatch Intelligence**: Recognizes solid black wall cuts (*poche*) and reconstructs them into **two independent editable CAD boundary lines (`A-WALL`) enclosing a native CAD `HATCH` entity (`A-HATCH`)**.
- **Scale Preservation**: Converts pixel space into real-world modelspace coordinates (feet, inches, meters, millimeters) via embedded scale bars, Matterport legend detection, or manual 2-point calibration.
- **Topological Cleanup**: Collinear line merging, endpoint snapping, intersection cleanup (L-junctions, T-junctions, cross intersections), and duplicate line removal.
- **Architectural Feature Recognition**: Identifies doors, 90° swing quadrant arcs, window glazing, and structural columns.
- **Industry Standard Semantic Layers**: Generates standardized CAD layers with AutoCAD Color Index (ACI) conventions.

---

## CAD Layer Specification

| Layer | Color (ACI) | Hex | Description |
|---|---|---|---|
| `A-WALL` | 7 (White/Black) | `#12151a` | Outer & inner wall boundary lines, partitions, and end caps |
| `A-HATCH` | 251 (Gray) | `#c5a059` | Native CAD solid hatch fills for wall cuts |
| `A-DOOR` | 1 (Red) | `#d9534f` | Door leafs, jambs, and 90° swing arcs |
| `A-GLAZ` | 4 (Cyan) | `#0288d1` | Windows, glazing, and curtain walls |
| `A-COLS` | 3 (Green) | `#2e7d32` | Structural column cuts and boundaries |
| `A-ANNO` | 2 (Yellow) | `#f57c00` | Dimension strokes, text, and annotations |
| `AV-REVIEW`| 1 (Red) | `#d32f2f` | Uncertain geometry flagged for operator confirmation |

---

## Application Architecture

```
AV_ras2/
├── engine/
│   ├── document.py          # Intake for PDF, JPG, PNG, TIFF, SVG; native vector extraction
│   ├── scale.py             # Scale calibration, Matterport legend detection, coordinate transforms
│   ├── preprocess.py        # Denoising, distance transform (stroke width), binarization
│   ├── wall_hatch.py        # Poche analysis, double boundary wall extraction, CAD hatch generation
│   ├── topology.py          # Collinear line merging, vertex snapping, duplicate removal
│   ├── architectural.py     # Door swing arcs, door leaves, window glazing detection
│   ├── cad_entities.py      # Intermediate dual-coordinate geometric representation
│   ├── export_dxf.py        # ezdxf R2010 AutoCAD export (modelspace, units, native hatches)
│   ├── export_svg.py        # Structured, layered SVG vector export
│   ├── export_pdf.py        # Crisp vector PDF drawing generator
│   ├── qa.py                # Alignment diagnostics, raster coverage %, residual calculation
│   └── pipeline.py          # Master conversion orchestrator
├── ui/
│   ├── index.html           # Artificial Vision branded UI (clean white, gold accents, dark text)
│   ├── styles.css           # Modern, responsive design system
│   └── app.js               # Interactive canvas, pan/zoom, calibration tool, layer toggles
├── tests/
│   ├── test_scale.py        # Scale calculation and coordinate mapping tests
│   ├── test_wall_hatch.py   # Critical: two boundary walls + native hatch tests
│   ├── test_topology.py     # Vertex snapping, collinear merging tests
│   ├── test_dxf_roundtrip.py# ezdxf readback, layer, entity, and unit verification
│   ├── test_end_to_end.py   # Full synthetic plan reconstruction & export verification
│   └── test_server.py       # REST API and webview endpoint verification
├── app.py                   # Standalone desktop application launcher (Edge WebView2 / browser)
├── cli.py                   # Command-line interface for batch and headless operations
└── requirements.txt         # Dependency manifest
```

---

## Getting Started

### 1. Requirements
- Python 3.10+
- Windows 10/11 (x64)

Install dependencies:
```bash
pip install -r requirements.txt
```

### 2. Launching the Standalone Desktop Application
Run:
```bash
python app.py
```
This launches AV Ras2 in a dedicated native Windows desktop window using Edge WebView2.
To launch directly into your default web browser, pass `--browser`:
```bash
python app.py --browser
```

### 3. Command-Line Batch Conversion
To convert a single plan or an entire folder of drawings from the command line:
```bash
# Convert a single raster image
python cli.py "samples/my_floor_plan.png" -o "output" --unit ft

# Batch convert a directory of plans
python cli.py "samples/matterport_exports/" -o "cad_drawings" --unit ft
```

---

## Automated QA and Testing

Run the full automated test suite:
```bash
python -m unittest discover tests
```

Tests include:
1. **Scale Intelligence (`test_scale.py`)**: 2-point calibration, multi-reference residual error, coordinate transformation math.
2. **Wall & Hatch Intelligence (`test_wall_hatch.py`)**: Validates that solid poche regions produce two independent wall boundaries and a native CAD HATCH.
3. **Topology Engine (`test_topology.py`)**: Collinear line merging, gap snapping, and duplicate elimination.
4. **DXF Roundtrip (`test_dxf_roundtrip.py`)**: Verifies the exported DXF file opens cleanly in `ezdxf`, checking entities, layers, and units.
5. **End-to-End Pipeline (`test_end_to_end.py`)**: Reconstructs a complete synthetic floor plan and verifies all deliverables.

---

## Third-Party Dependency & License Inventory

| Library | Version | License | Purpose |
|---|---|---|---|
| `ezdxf` | >= 1.4.0 | MIT | Native AutoCAD DXF file generation and parsing |
| `opencv-python` | >= 4.8.0 | Apache 2.0 | Computer vision, filtering, contour extraction, Hough transforms |
| `scikit-image` | >= 0.22.0 | BSD 3-Clause | Image processing algorithms |
| `numpy` | >= 1.26.0 | BSD 3-Clause | High-performance numerical computations |
| `scipy` | >= 1.11.0 | BSD 3-Clause | Spatial algorithms and distance calculations |
| `shapely` | >= 2.0.0 | BSD 3-Clause | 2D computational geometry and polygon operations |
| `pymupdf` | >= 1.23.0 | AGPL / Commercial | High-resolution PDF rendering and vector path inspection |
| `pillow` | >= 10.0.0 | HPND | Image decoding and format handling |
| `pywebview` | >= 5.0.0 | BSD 3-Clause | Native Windows Edge WebView2 desktop container |
| `bottle` | >= 0.13.0 | MIT | Micro WSGI web framework for local IPC |

---

## Artificial Vision, Inc.
*Find your sense.*
All rights reserved.
