"""AV Ras2 Conversion Pipeline Orchestrator.

Coordinates complete conversion from locked raster floor plan to verified,
scaled CAD drawing with architectural layers and native hatches.
"""

import os
from typing import Any, Dict, List, Optional, Tuple
import cv2
import numpy as np

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
from .document import DocumentLoader, DocumentPage, DocumentIntakeResult
from .scale import ScaleContext, ScaleEngine, Unit
from .preprocess import RasterPreprocessor, PreprocessedResult
from .wall_hatch import WallHatchIntelligence, ReconstructedWall
from .topology import CADTopologyEngine
from .architectural import ArchitecturalFeatureRecognizer
from .qa import CADQualityAssurance
from .export_dxf import DXFExportEngine
from .export_svg import SVGExportEngine
from .export_pdf import PDFExportEngine


class ConversionPipeline:
    """Master pipeline converting raster floor plans to structured vector CAD."""

    def __init__(self):
        pass

    def run(
        self,
        image_or_path: Any,
        page_num: int = 1,
        manual_scale_pts: Optional[Tuple[Tuple[float, float], Tuple[float, float], float]] = None,
        unit: Unit = Unit.FEET,
        target_dpi: int = 150,
        output_dir: Optional[str] = None,
        plan_name: str = "reconstructed_plan",
        external_text_blocks: Optional[List[Dict[str, Any]]] = None,
    ) -> ReconstructedPlan:
        """Execute full conversion pipeline."""
        # 1. Load document page
        text_blocks_raw = external_text_blocks or []
        if isinstance(image_or_path, str):
            intake = DocumentLoader.load_document(image_or_path, target_dpi=target_dpi)
            target_page = intake.pages[min(page_num - 1, len(intake.pages) - 1)]
            img_bgr = target_page.image_np
            if not plan_name or plan_name == "reconstructed_plan":
                plan_name = os.path.splitext(os.path.basename(image_or_path))[0]
            if not text_blocks_raw and target_page.text_blocks:
                text_blocks_raw = target_page.text_blocks
        elif isinstance(image_or_path, np.ndarray):
            img_bgr = image_or_path
        else:
            raise ValueError("image_or_path must be a file path string or numpy array.")

        h, w = img_bgr.shape[:2]

        # 2. Establish Scale
        if manual_scale_pts is not None:
            p1, p2, dist = manual_scale_pts
            scale_ctx = ScaleEngine.calibrate_from_two_points(
                p1=p1, p2=p2, real_dist=dist, unit=unit, img_width=float(w), img_height=float(h)
            )
        else:
            scale_ctx = ScaleEngine.detect_matterport_scale_bar(img_bgr)
            if scale_ctx is None and text_blocks_raw:
                scale_ctx = ScaleEngine.calibrate_from_dimension_annotations(
                    text_blocks_raw, float(w), float(h), unit=unit
                )
            if scale_ctx is None:
                # Default architectural scale fallback (0.03 ft per pixel at 150 DPI)
                scale_ctx = ScaleContext(
                    units_per_pixel=0.03,
                    unit=unit,
                    image_width=float(w),
                    image_height=float(h),
                    method="default_scale",
                    confidence=0.70,
                )

        # 3. Text and Dimension Extraction
        import re
        text_entities: List[CADText] = []
        text_bboxes_px: List[Tuple[float, float, float, float]] = []

        dim_pattern = re.compile(r"(\d+['\’]\d+[\"”]|[\d\.]+\s*(?:m|ft|in|sq))", re.IGNORECASE)

        for blk in text_blocks_raw:
            txt_str = blk.get("text", "").strip()
            if not txt_str:
                continue

            bbox = blk.get("bbox_px", (0, 0, 0, 0))
            text_bboxes_px.append(bbox)

            # Determine insertion point (bottom-left of text box)
            insert_px = (bbox[0], bbox[3])
            insert_cad = scale_ctx.px_to_cad(insert_px[0], insert_px[1])
            h_px = blk.get("height_px", 14.0)
            h_cad = max(0.4, scale_ctx.px_dist_to_cad(h_px) * 0.7)

            # Layer classification: dimensions vs annotations
            is_dim = bool(dim_pattern.search(txt_str))
            target_layer = CADLayer.DIMENSIONS if is_dim else CADLayer.ANNOTATION

            cad_txt = CADText(
                layer=target_layer,
                confidence=0.99,
                source_evidence="document_text_string",
                text_string=txt_str,
                insert_px=insert_px,
                insert_cad=insert_cad,
                height_px=h_px,
                height_cad=h_cad,
                rotation_deg=0.0,
                bbox_px=bbox,
            )
            text_entities.append(cad_txt)

        # 4. Preprocessing with Text Masking
        # Mask out text bounding boxes so letters are NOT converted to lines!
        prep: PreprocessedResult = RasterPreprocessor.process(
            img_bgr,
            known_text_bboxes=text_bboxes_px if text_bboxes_px else None
        )

        # 5. Critical Wall and Hatch Intelligence
        wall_engine = WallHatchIntelligence(scale_ctx)
        reconstructed_walls: List[ReconstructedWall] = wall_engine.reconstruct_from_masks(
            binary_drawing=prep.binary,
            thick_regions_mask=prep.thick_regions_mask,
            distance_map=prep.distance_map,
        )

        all_entities: List[CADEntity] = []

        # Collect wall boundaries and native hatches
        wall_lines_for_cleanup: List[CADLine] = []

        for rw in reconstructed_walls:
            # Add native CAD HATCH
            all_entities.append(rw.hatch_entity)
            # Collect boundaries
            for b_ent in rw.boundary_entities:
                if isinstance(b_ent, CADLine):
                    wall_lines_for_cleanup.append(b_ent)
                else:
                    all_entities.append(b_ent)

        # 6. CAD Topology Cleanup on straight wall boundaries
        topo_engine = CADTopologyEngine(scale_ctx, snap_distance_px=3.0)
        cleaned_wall_lines = topo_engine.clean_lines(wall_lines_for_cleanup)
        all_entities.extend(cleaned_wall_lines)

        # 7. Architectural Recognition (Doors, Swings, Glazing, Fixtures)
        arch_engine = ArchitecturalFeatureRecognizer(scale_ctx)
        door_entities, detected_doors, remaining_thin_mask = arch_engine.detect_doors_and_arcs(
            thin_lines_mask=prep.thin_lines_mask,
            binary_mask=prep.binary,
        )
        all_entities.extend(door_entities)

        # Thin straight features (glazing, partitions, stairs) from remaining mask
        # Door arcs have been erased from remaining_thin_mask so no broken chords are generated!
        thin_lines = arch_engine.detect_straight_thin_features(remaining_thin_mask)
        all_entities.extend(thin_lines)

        # Add native CAD Text entities
        all_entities.extend(text_entities)

        # 8. Construct Plan
        plan = ReconstructedPlan(
            plan_name=plan_name,
            scale_context=scale_ctx,
            entities=all_entities,
            raster_width=w,
            raster_height=h,
            metadata={
                "doors_count": len(detected_doors),
                "walls_count": len(reconstructed_walls),
                "text_count": len(text_entities),
                "scale_method": scale_ctx.method,
            },
        )

        # 8. QA Evaluation
        CADQualityAssurance.evaluate(plan, prep.binary)

        # 9. Optional Export
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            dxf_path = os.path.join(output_dir, f"{plan_name}.dxf")
            svg_path = os.path.join(output_dir, f"{plan_name}.svg")
            pdf_path = os.path.join(output_dir, f"{plan_name}.pdf")
            overlay_path = os.path.join(output_dir, f"{plan_name}_overlay.png")

            DXFExportEngine.export(plan, dxf_path)
            SVGExportEngine.export(plan, svg_path)
            PDFExportEngine.export(plan, pdf_path)

            overlay_img = CADQualityAssurance.generate_diagnostic_overlay(img_bgr, plan)
            cv2.imwrite(overlay_path, overlay_img)

            plan.metadata["exported_files"] = {
                "dxf": dxf_path,
                "svg": svg_path,
                "pdf": pdf_path,
                "overlay": overlay_path,
            }

        return plan
