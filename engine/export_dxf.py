"""AV Ras2 DXF Export Engine.

Generates genuine, production-grade DXF drawings using ezdxf.
Supports:
- Model-space Cartesian real-world coordinates
- Correct unit header variables ($INSUNITS)
- Architectural layer hierarchy with standardized ACI colors
- Native CAD entities: LINE, LWPOLYLINE, ARC, and native CAD HATCH
- Round-trip validation compatibility with AutoCAD, BricsCAD, and Revit.
"""

from typing import Dict, List, Optional
import ezdxf
from ezdxf import units

from .cad_entities import (
    CADEntity,
    CADLine,
    CADPolyline,
    CADArc,
    CADHatch,
    CADText,
    CADLayer,
    LAYER_COLORS,
    ReconstructedPlan,
    EntityType,
)
from .scale import Unit


# Map Unit enum to ezdxf $INSUNITS constants
INSUNITS_MAP = {
    Unit.FEET: units.FT,
    Unit.INCHES: units.IN,
    Unit.METERS: units.M,
    Unit.MILLIMETERS: units.MM,
    Unit.CENTIMETERS: units.CM,
}


class DXFExportEngine:
    """Exports ReconstructedPlan to AutoCAD-compatible DXF."""

    @classmethod
    def export(
        cls,
        plan: ReconstructedPlan,
        output_path: str,
        dxf_version: str = "R2010",
        enabled_layers: Optional[List[CADLayer]] = None,
    ) -> str:
        """Export plan geometry to a valid DXF file."""
        doc = ezdxf.new(dxfversion=dxf_version, setup=True)

        # Set drawing units
        unit_enum = plan.scale_context.unit if hasattr(plan.scale_context, "unit") else Unit.FEET
        insunit = INSUNITS_MAP.get(unit_enum, units.FT)
        doc.header["$INSUNITS"] = insunit
        doc.header["$MEASUREMENT"] = 1 if unit_enum in [Unit.METERS, Unit.MILLIMETERS, Unit.CENTIMETERS] else 0

        # Create standardized layers
        cls._setup_layers(doc)

        msp = doc.modelspace()
        layers_to_export = set(enabled_layers) if enabled_layers else set(CADLayer)

        for entity in plan.entities:
            if entity.layer not in layers_to_export:
                continue

            try:
                if entity.entity_type == EntityType.LINE and isinstance(entity, CADLine):
                    cls._write_line(msp, entity)
                elif entity.entity_type == EntityType.LWPOLYLINE and isinstance(entity, CADPolyline):
                    cls._write_polyline(msp, entity)
                elif entity.entity_type == EntityType.ARC and isinstance(entity, CADArc):
                    cls._write_arc(msp, entity)
                elif entity.entity_type == EntityType.HATCH and isinstance(entity, CADHatch):
                    cls._write_hatch(msp, entity)
                elif entity.entity_type == EntityType.TEXT and isinstance(entity, CADText):
                    cls._write_text(msp, entity)
            except Exception as e:
                # Log error and continue with remaining geometry
                print(f"Warning writing entity {entity.id} ({entity.entity_type}): {e}")

        doc.saveas(output_path)
        return output_path

    @classmethod
    def _setup_layers(cls, doc: ezdxf.document.Drawing):
        """Create layers with standardized architectural colors."""
        for layer_enum in CADLayer:
            color = LAYER_COLORS.get(layer_enum, 7)
            if layer_enum.value not in doc.layers:
                doc.layers.add(
                    name=layer_enum.value,
                    color=color,
                    linetype="CONTINUOUS",
                )

    @classmethod
    def _write_line(cls, msp, line: CADLine):
        msp.add_line(
            start=line.start_cad,
            end=line.end_cad,
            dxfattribs={
                "layer": line.layer.value,
                "color": LAYER_COLORS.get(line.layer, 7),
            },
        )

    @classmethod
    def _write_polyline(cls, msp, poly: CADPolyline):
        if len(poly.points_cad) < 2:
            return
        msp.add_lwpolyline(
            points=poly.points_cad,
            close=poly.is_closed,
            dxfattribs={
                "layer": poly.layer.value,
                "color": LAYER_COLORS.get(poly.layer, 7),
            },
        )

    @classmethod
    def _write_arc(cls, msp, arc: CADArc):
        msp.add_arc(
            center=arc.center_cad,
            radius=arc.radius_cad,
            start_angle=arc.start_angle_deg,
            end_angle=arc.end_angle_deg,
            dxfattribs={
                "layer": arc.layer.value,
                "color": LAYER_COLORS.get(arc.layer, 7),
            },
        )

    @classmethod
    def _write_hatch(cls, msp, hatch_entity: CADHatch):
        """Generate a genuine native CAD HATCH entity."""
        if not hatch_entity.loops_cad:
            return

        hatch = msp.add_hatch(
            color=LAYER_COLORS.get(hatch_entity.layer, 251),
            dxfattribs={
                "layer": hatch_entity.layer.value,
            },
        )
        hatch.set_pattern_fill(
            hatch_entity.pattern_name,
            color=LAYER_COLORS.get(hatch_entity.layer, 251),
            scale=1.0,
        )

        for loop_pts in hatch_entity.loops_cad:
            if len(loop_pts) >= 3:
                # Add closed polyline path to hatch boundary
                hatch.paths.add_polyline_path(loop_pts, is_closed=True)

    @classmethod
    def _write_text(cls, msp, text_ent: CADText):
        """Add native CAD TEXT entity."""
        if not text_ent.text_string:
            return
        lines = text_ent.text_string.split("\n")
        line_height = max(0.2, text_ent.height_cad)
        x_base, y_base = text_ent.insert_cad

        for i, line_str in enumerate(lines):
            clean_str = line_str.strip()
            if not clean_str:
                continue
            y_pos = y_base - (i * line_height * 1.35)
            txt = msp.add_text(
                clean_str,
                height=line_height,
                rotation=text_ent.rotation_deg,
                dxfattribs={
                    "layer": text_ent.layer.value,
                    "color": LAYER_COLORS.get(text_ent.layer, 2),
                },
            )
            txt.set_placement((x_base, y_pos))
