# AV Ras2 — Master Prompt & Engineering Specification
**Artificial Vision, Inc.** | *Find your sense.*  
Website: [https://artificialviz.com](https://artificialviz.com)

---

## 1. Project Identity
- **Product Name**: AV Ras2
- **Company**: Artificial Vision, Inc.
- **Website**: https://artificialviz.com
- **Tagline**: *Find your sense.*
- **Primary Platform**: Windows 10/11, 64-bit
- **Application Type**: Standalone desktop software
- **Primary Industry**: Architecture, Engineering, Construction (AEC), Reality Capture, BIM/VDC

---

## 2. Primary Objective
Convert locked raster floor plans—specifically Matterport exports, schematic floor plans, and flattened architectural PDFs—into clean, scaled, and properly layered vector CAD geometry (`.dxf`, `.svg`, `.pdf`), rather than merely tracing pixels.

### Non-Negotiable Core Principles:
1. **Real Functional Conversion**: No simulated results or dummy endpoints.
2. **CAD Correctness over Visual Similarity**: Straight continuous lines instead of jagged pixel edges.
3. **Local-First & Offline**: Zero mandatory cloud services, subscriptions, external accounts, or pay-per-credit AI APIs.
4. **Scale Preservation**: Real-world modelspace coordinates (feet, inches, meters, millimeters).
5. **CRITICAL WALL & HATCH RULE**: Solid black wall cuts (*poche*) must be reconstructed into **two independent editable wall boundary lines (`A-WALL`) enclosing an independent native CAD `HATCH` entity (`A-HATCH`, pattern `SOLID`)**. Walls must never be converted into a single centerline, thick polyline, or thousands of traced pixel boundaries.

---

## 3. Technology Stack

| Component | Technology | Rationale |
|---|---|---|
| Frontend UI | HTML5 Canvas, Vanilla JS, CSS3 | Clean white, gold accents (`#c5a059`), dark typography, high-performance pan/zoom |
| Desktop Container | PyWebView / Edge WebView2 | Native Windows desktop runtime without heavy separate Electron bundling |
| Local Server | Python Bottle WSGI | Zero-overhead, zero-dependency local IPC |
| Image Processing | OpenCV (`cv2`), NumPy, SciPy | Morphological analysis, distance transform, connected components |
| PDF & Vectors | PyMuPDF (`fitz`) | Multi-page rendering, native text string extraction, vector path inspection |
| CAD Export | `ezdxf` (MIT licensed) | AutoCAD R2010/R2018 DXF with modelspace, layers, native SOLID hatches |
| Computational Geometry | Shapely | Polygon simplification, boundary extraction, topology |

---

## 4. Standard Architectural CAD Layers

| Layer | Color (ACI) | Hex | Description |
|---|---|---|---|
| `A-WALL` | 7 (White/Black) | `#12151a` | Outer & inner wall boundary lines, partitions, end caps |
| `A-HATCH` | 251 (Gray) | `#c5a059` | Native CAD solid hatch fills for wall cuts |
| `A-DOOR` | 1 (Red) | `#d9534f` | Door leaves, jambs, and 90° circular quadrant swing arcs |
| `A-GLAZ` | 4 (Cyan) | `#0288d1` | Windows, glazing, and curtain walls |
| `A-COLS` | 3 (Green) | `#2e7d32` | Structural column cuts and boundaries |
| `A-STRS` | 6 (Magenta) | `#8e24aa` | Stairs and rungs |
| `A-FIXT` | 5 (Blue) | `#1976d2` | Architectural fixtures (toilets, tubs, sinks) |
| `A-FLOR` | 8 (Dark Gray) | `#757575` | Floor boundaries and perimeter lines |
| `A-ANNO` | 2 (Yellow) | `#f57c00` | Room names, labels, and notes |
| `A-DIMS` | 2 (Yellow) | `#f57c00` | Dimension strings |
| `AV-REVIEW`| 1 (Red) | `#d32f2f` | Uncertain geometry flagged for operator confirmation |

---

## 5. Development Milestones

- **M0 — Architecture & Foundation**: Modular architecture, data models, and dependencies.
- **M1 — Document Intake & Multi-page Support**: PDF/raster ingestion, DPI resolution management.
- **M2 — Scale Intelligence**: 2-point manual calibration, Matterport scale bar detection, room dimension annotation calibration.
- **M3 — Raster Geometry Extraction**: Non-destructive binarization, stroke-width distance transforms.
- **M4 — Wall & Hatch Intelligence**: Thick line vs. poche classification, double boundary wall generation, native CAD HATCH.
- **M5 — CAD Topology & Orthogonal Rectification**: Endpoint snapping, collinear merging, Manhattan angle rectification.
- **M6 — Architectural Object Recognition**: Door swings (90° quadrant arcs), windows, fixtures, stairs.
- **M7 — CAD Export Engine**: Genuine AutoCAD DXF (R2010), vector PDF, layered SVG, diagnostic QA overlay.
- **M8 — GUI Editing & QA**: Dual overlay comparison, opacity slider, layer toggles, entity property inspector.
- **M9 — Batch CLI & Headless Pipeline**: Parallel and sequential folder batch processing.
- **M10 — Windows Packaging & Regression Suite**: Automated test suite, desktop launcher batch script, comprehensive documentation.
