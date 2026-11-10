"""AV Ras2 Vector PDF Export Engine.

Generates high-resolution vector PDF documents using PyMuPDF vector drawing primitives.
"""

from typing import List, Optional
import fitz
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

PDF_COLORS = {
    CADLayer.WALL: (0.1, 0.1, 0.1),
    CADLayer.DOOR: (0.85, 0.32, 0.31),
    CADLayer.GLAZING: (0.01, 0.53, 0.82),
    CADLayer.COLUMNS: (0.18, 0.49, 0.20),
    CADLayer.STAIRS: (0.55, 0.14, 0.66),
    CADLayer.FLOOR: (0.45, 0.45, 0.45),
    CADLayer.HATCH: (0.15, 0.15, 0.15),
    CADLayer.ANNOTATION: (0.96, 0.48, 0.0),
    CADLayer.REVIEW: (0.83, 0.18, 0.18),
}


class PDFExportEngine:
    @classmethod
    def export(cls, plan: ReconstructedPlan, output_path: str) -> str:
        doc = fitz.open()
        w_pt = float(plan.raster_width) * 72.0 / 150.0
        h_pt = float(plan.raster_height) * 72.0 / 150.0

        page = doc.new_page(width=w_pt, height=h_pt)
        scale_x = w_pt / float(plan.raster_width)
        scale_y = h_pt / float(plan.raster_height)

        shape = page.new_shape()

        # Render Hatch fills first (background)
        hatch_entities = [e for e in plan.entities if e.entity_type == EntityType.HATCH and isinstance(e, CADHatch)]
        for h_ent in hatch_entities:
            color = PDF_COLORS.get(h_ent.layer, (0.2, 0.2, 0.2))
            for loop in h_ent.loops_px:
                if len(loop) >= 3:
                    pts = [fitz.Point(p[0] * scale_x, p[1] * scale_y) for p in loop]
                    shape.draw_polyline(pts)
                    shape.finish(fill=color, color=None, closePath=True)

        # Render Linework
        other_entities = [e for e in plan.entities if e.entity_type != EntityType.HATCH]
        for ent in other_entities:
            color = PDF_COLORS.get(ent.layer, (0.1, 0.1, 0.1))
            if ent.entity_type == EntityType.LINE and isinstance(ent, CADLine):
                p1 = fitz.Point(ent.start_px[0] * scale_x, ent.start_px[1] * scale_y)
                p2 = fitz.Point(ent.end_px[0] * scale_x, ent.end_px[1] * scale_y)
                shape.draw_line(p1, p2)
                shape.finish(color=color, width=1.2)

            elif ent.entity_type == EntityType.LWPOLYLINE and isinstance(ent, CADPolyline):
                if len(ent.points_px) >= 2:
                    pts = [fitz.Point(p[0] * scale_x, p[1] * scale_y) for p in ent.points_px]
                    shape.draw_polyline(pts)
                    shape.finish(color=color, width=1.5, closePath=ent.is_closed)

            elif ent.entity_type == EntityType.ARC and isinstance(ent, CADArc):
                # Approximate arc with line segments
                import math
                cx, cy = ent.center_px
                r = ent.radius_px
                rad_s = math.radians(ent.start_angle_deg)
                rad_e = math.radians(ent.end_angle_deg)
                steps = 16
                d_theta = (rad_e - rad_s) / steps
                arc_pts = []
                for step in range(steps + 1):
                    theta = rad_s + step * d_theta
                    x = (cx + r * math.cos(theta)) * scale_x
                    y = (cy + r * math.sin(theta)) * scale_y
                    arc_pts.append(fitz.Point(x, y))
                if len(arc_pts) >= 2:
                    shape.draw_polyline(arc_pts)
                    shape.finish(color=color, width=1.0)

        shape.commit()

        # Render Text entities
        text_entities = [e for e in plan.entities if e.entity_type == EntityType.TEXT and isinstance(e, CADText)]
        for t_ent in text_entities:
            pt = fitz.Point(t_ent.insert_px[0] * scale_x, t_ent.insert_px[1] * scale_y)
            fontsize = max(8.0, t_ent.height_px * scale_y * 0.7)
            page.insert_text(pt, t_ent.text_string.replace("\n", " "), fontsize=fontsize, color=(0.85, 0.45, 0.0))

        doc.save(output_path)
        doc.close()
        return output_path
