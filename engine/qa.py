"""AV Ras2 Automated Quality Assurance & Diagnostic Overlay Engine.

Computes coverage metrics, residual error, topology health, and generates
diagnostic overlay images comparing reconstructed CAD entities against source raster.
"""

from typing import Any, Dict, List, Tuple
import cv2
import numpy as np

from .cad_entities import (
    CADEntity,
    CADLine,
    CADPolyline,
    CADArc,
    CADHatch,
    CADLayer,
    ReconstructedPlan,
    EntityType,
)


class CADQualityAssurance:
    """Performs geometric and topological validation of reconstructed CAD plans."""

    @classmethod
    def evaluate(cls, plan: ReconstructedPlan, original_binary: np.ndarray) -> Dict[str, Any]:
        """Compute QA metrics and validate geometry."""
        h, w = original_binary.shape[:2]
        cad_render_mask = np.zeros((h, w), dtype=np.uint8)

        wall_count = 0
        door_count = 0
        glaz_count = 0
        col_count = 0
        hatch_count = 0
        uncertain_count = 0

        # Draw CAD geometry onto test raster mask to measure raster coverage
        for ent in plan.entities:
            if ent.needs_review or ent.confidence < 0.70:
                uncertain_count += 1

            if ent.layer == CADLayer.WALL:
                wall_count += 1
            elif ent.layer == CADLayer.DOOR:
                door_count += 1
            elif ent.layer == CADLayer.GLAZING:
                glaz_count += 1
            elif ent.layer == CADLayer.COLUMNS:
                col_count += 1
            elif ent.layer == CADLayer.HATCH:
                hatch_count += 1

            # Render onto coverage mask
            if ent.entity_type == EntityType.LINE and isinstance(ent, CADLine):
                p1 = (int(round(ent.start_px[0])), int(round(ent.start_px[1])))
                p2 = (int(round(ent.end_px[0])), int(round(ent.end_px[1])))
                cv2.line(cad_render_mask, p1, p2, 255, 3)

            elif ent.entity_type == EntityType.LWPOLYLINE and isinstance(ent, CADPolyline):
                pts = np.array([[int(round(p[0])), int(round(p[1]))] for p in ent.points_px], dtype=np.int32)
                if len(pts) >= 2:
                    cv2.polylines(cad_render_mask, [pts], ent.is_closed, 255, 3)

            elif ent.entity_type == EntityType.HATCH and isinstance(ent, CADHatch):
                for loop in ent.loops_px:
                    pts = np.array([[int(round(p[0])), int(round(p[1]))] for p in loop], dtype=np.int32)
                    if len(pts) >= 3:
                        cv2.fillPoly(cad_render_mask, [pts], 255)

        # Calculate coverage overlap
        raster_fg_pixels = np.count_nonzero(original_binary)
        if raster_fg_pixels > 0:
            overlap = cv2.bitwise_and(original_binary, cad_render_mask)
            overlap_pixels = np.count_nonzero(overlap)
            coverage_pct = round((overlap_pixels / float(raster_fg_pixels)) * 100.0, 1)
        else:
            coverage_pct = 100.0

        scale_ctx = plan.scale_context
        residual_err = scale_ctx.residual_error if hasattr(scale_ctx, "residual_error") else 0.0

        qa_report = {
            "raster_coverage_pct": coverage_pct,
            "total_entities": len(plan.entities),
            "walls_detected": wall_count,
            "doors_detected": door_count,
            "glazing_detected": glaz_count,
            "columns_detected": col_count,
            "hatch_regions": hatch_count,
            "uncertain_entities": uncertain_count,
            "calibration_residual": round(residual_err, 4),
            "scale_units": scale_ctx.unit.value if hasattr(scale_ctx, "unit") else "ft",
            "scale_ratio": round(scale_ctx.units_per_pixel, 6) if hasattr(scale_ctx, "units_per_pixel") else 0.0,
            "status": "PASS" if coverage_pct >= 60.0 and uncertain_count < len(plan.entities) * 0.3 else "REVIEW_RECOMMENDED",
        }

        plan.qa_report = qa_report
        return qa_report

    @classmethod
    def generate_diagnostic_overlay(
        cls,
        original_bgr: np.ndarray,
        plan: ReconstructedPlan,
        alpha: float = 0.5,
    ) -> np.ndarray:
        """Create visual overlay: Original drawing in muted gray, CAD linework in vivid colors."""
        h, w = original_bgr.shape[:2]
        gray = cv2.cvtColor(original_bgr, cv2.COLOR_BGR2GRAY)
        muted_base = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        # Lighten background slightly
        muted_base = cv2.addWeighted(muted_base, 0.7, np.full_like(muted_base, 255), 0.3, 0)

        overlay = muted_base.copy()

        # Render Hatch regions in translucent gold
        for ent in plan.entities:
            if ent.entity_type == EntityType.HATCH and isinstance(ent, CADHatch):
                for loop in ent.loops_px:
                    pts = np.array([[int(round(p[0])), int(round(p[1]))] for p in loop], dtype=np.int32)
                    if len(pts) >= 3:
                        cv2.fillPoly(overlay, [pts], (80, 160, 212))  # Artificial Vision Gold accent

        # Blend hatch
        blended = cv2.addWeighted(overlay, alpha, muted_base, 1.0 - alpha, 0)

        # Draw CAD Linework on top with crisp anti-aliasing
        for ent in plan.entities:
            if ent.entity_type == EntityType.LINE and isinstance(ent, CADLine):
                color = (0, 0, 230) if ent.layer == CADLayer.DOOR else (30, 30, 30)
                p1 = (int(round(ent.start_px[0])), int(round(ent.start_px[1])))
                p2 = (int(round(ent.end_px[0])), int(round(ent.end_px[1])))
                cv2.line(blended, p1, p2, color, 2, cv2.LINE_AA)

            elif ent.entity_type == EntityType.LWPOLYLINE and isinstance(ent, CADPolyline):
                pts = np.array([[int(round(p[0])), int(round(p[1]))] for p in ent.points_px], dtype=np.int32)
                if len(pts) >= 2:
                    cv2.polylines(blended, [pts], ent.is_closed, (30, 30, 30), 2, cv2.LINE_AA)

            elif ent.entity_type == EntityType.ARC and isinstance(ent, CADArc):
                cx, cy = int(round(ent.center_px[0])), int(round(ent.center_px[1]))
                r = int(round(ent.radius_px))
                cv2.ellipse(
                    blended,
                    (cx, cy),
                    (r, r),
                    0,
                    ent.start_angle_deg,
                    ent.end_angle_deg,
                    (0, 0, 230),
                    2,
                    cv2.LINE_AA,
                )

        return blended
