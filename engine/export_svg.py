"""AV Ras2 SVG Export Engine.

Exports reconstructed CAD geometry as high-fidelity SVG with layer grouping.
"""

from typing import List, Optional
import math
from .cad_entities import (
    CADEntity,
    CADLine,
    CADPolyline,
    CADArc,
    CADHatch,
    CADText,
    CADLayer,
    ReconstructedPlan,
    EntityType,
)

LAYER_HEX_COLORS = {
    CADLayer.WALL: "#1a1a1a",
    CADLayer.DOOR: "#d9534f",
    CADLayer.GLAZING: "#0288d1",
    CADLayer.COLUMNS: "#2e7d32",
    CADLayer.STAIRS: "#8e24aa",
    CADLayer.FLOOR: "#757575",
    CADLayer.HATCH: "#333333",
    CADLayer.ANNOTATION: "#f57c00",
    CADLayer.DIMENSIONS: "#f57c00",
    CADLayer.REVIEW: "#d32f2f",
}


class SVGExportEngine:
    @classmethod
    def export(cls, plan: ReconstructedPlan, output_path: str, use_pixel_coords: bool = True) -> str:
        w = plan.raster_width
        h = plan.raster_height

        lines = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">',
            '  <defs>',
            '    <pattern id="diagonalHatch" width="10" height="10" patternTransform="rotate(45 0 0)" patternUnits="userSpaceOnUse">',
            '      <line x1="0" y1="0" x2="0" y2="10" stroke="#555" stroke-width="1.5" />',
            '    </pattern>',
            '  </defs>',
            '  <style>',
            '    .A-WALL { stroke: #1a1a1a; stroke-width: 2.0; fill: none; stroke-linecap: round; stroke-linejoin: round; }',
            '    .A-DOOR { stroke: #d9534f; stroke-width: 1.5; fill: none; }',
            '    .A-GLAZ { stroke: #0288d1; stroke-width: 1.5; fill: none; }',
            '    .A-COLS { stroke: #2e7d32; stroke-width: 2.0; fill: #a5d6a7; fill-opacity: 0.5; }',
            '    .A-HATCH { fill: #222222; fill-opacity: 0.85; stroke: none; }',
            '    .A-ANNO { stroke: #f57c00; stroke-width: 1.0; fill: none; }',
            '    .AV-REVIEW { stroke: #d32f2f; stroke-width: 2.0; stroke-dasharray: 4,4; fill: none; }',
            '  </style>',
        ]

        # Group by layers
        for layer_enum in CADLayer:
            layer_entities = [e for e in plan.entities if e.layer == layer_enum]
            if not layer_entities:
                continue

            lines.append(f'  <g id="{layer_enum.value}" class="{layer_enum.value}">')
            for e in layer_entities:
                if e.entity_type == EntityType.LINE and isinstance(e, CADLine):
                    p1, p2 = e.start_px, e.end_px
                    lines.append(f'    <line x1="{p1[0]:.2f}" y1="{p1[1]:.2f}" x2="{p2[0]:.2f}" y2="{p2[1]:.2f}" id="{e.id}" />')

                elif e.entity_type == EntityType.LWPOLYLINE and isinstance(e, CADPolyline):
                    pts_str = " ".join([f"{p[0]:.2f},{p[1]:.2f}" for p in e.points_px])
                    tag = "polygon" if e.is_closed else "polyline"
                    lines.append(f'    <{tag} points="{pts_str}" id="{e.id}" />')

                elif e.entity_type == EntityType.ARC and isinstance(e, CADArc):
                    cx, cy = e.center_px
                    r = e.radius_px
                    rad_s = math.radians(e.start_angle_deg)
                    rad_e = math.radians(e.end_angle_deg)
                    x1 = cx + r * math.cos(rad_s)
                    y1 = cy + r * math.sin(rad_s)
                    x2 = cx + r * math.cos(rad_e)
                    y2 = cy + r * math.sin(rad_e)
                    large_arc = 1 if (e.end_angle_deg - e.start_angle_deg) > 180 else 0
                    d = f"M {x1:.2f} {y1:.2f} A {r:.2f} {r:.2f} 0 {large_arc} 1 {x2:.2f} {y2:.2f}"
                    lines.append(f'    <path d="{d}" id="{e.id}" />')

                elif e.entity_type == EntityType.HATCH and isinstance(e, CADHatch):
                    path_d = []
                    for loop in e.loops_px:
                        if len(loop) >= 3:
                            loop_d = f"M {loop[0][0]:.2f} {loop[0][1]:.2f} " + " ".join([f"L {pt[0]:.2f} {pt[1]:.2f}" for pt in loop[1:]]) + " Z"
                            path_d.append(loop_d)
                    if path_d:
                        full_d = " ".join(path_d)
                        lines.append(f'    <path d="{full_d}" fill-rule="evenodd" id="{e.id}" />')

                elif e.entity_type == EntityType.TEXT and isinstance(e, CADText):
                    x, y = e.insert_px
                    h_val = max(10.0, e.height_px * 0.7)
                    escaped_str = e.text_string.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", " ")
                    lines.append(f'    <text x="{x:.2f}" y="{y:.2f}" font-size="{h_val:.1f}" font-family="sans-serif" font-weight="600" fill="#f57c00" id="{e.id}">{escaped_str}</text>')

            lines.append('  </g>')

        lines.append('</svg>')

        svg_content = "\n".join(lines)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(svg_content)
        return output_path
