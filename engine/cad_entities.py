"""AV Ras2 CAD Geometric Entities & Data Models.

Defines the intermediate geometric representation independent of export format.
Every entity maintains dual coordinates (pixel space & CAD real-world space),
semantic CAD layering, confidence scores, and architectural metadata.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import uuid


class CADLayer(str, Enum):
    WALL = "A-WALL"
    DOOR = "A-DOOR"
    GLAZING = "A-GLAZ"
    COLUMNS = "A-COLS"
    STAIRS = "A-STRS"
    FIXTURES = "A-FIXT"
    FLOOR = "A-FLOR"
    HATCH = "A-HATCH"
    ANNOTATION = "A-ANNO"
    DIMENSIONS = "A-DIMS"
    REVIEW = "AV-REVIEW"


LAYER_COLORS: Dict[CADLayer, int] = {
    # AutoCAD Color Index (ACI)
    CADLayer.WALL: 7,       # White / Black
    CADLayer.DOOR: 1,       # Red
    CADLayer.GLAZING: 4,    # Cyan
    CADLayer.COLUMNS: 3,    # Green
    CADLayer.STAIRS: 6,     # Magenta
    CADLayer.FIXTURES: 5,   # Blue
    CADLayer.FLOOR: 8,      # Dark Gray
    CADLayer.HATCH: 251,    # Light / Dark Gray fill
    CADLayer.ANNOTATION: 2, # Yellow
    CADLayer.DIMENSIONS: 2, # Yellow
    CADLayer.REVIEW: 1,     # Red for attention
}


class EntityType(str, Enum):
    LINE = "LINE"
    LWPOLYLINE = "LWPOLYLINE"
    ARC = "ARC"
    CIRCLE = "CIRCLE"
    HATCH = "HATCH"
    TEXT = "TEXT"


@dataclass
class Point2D:
    x: float
    y: float

    def to_tuple(self) -> Tuple[float, float]:
        return (self.x, self.y)

    def dist_to(self, other: "Point2D") -> float:
        import math
        return math.hypot(self.x - other.x, self.y - other.y)


@dataclass
class CADEntity:
    """Base CAD Entity representation."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    entity_type: EntityType = EntityType.LINE
    layer: CADLayer = CADLayer.WALL
    confidence: float = 1.0
    needs_review: bool = False
    source_evidence: str = "detected"
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Pixel space coordinates (for viewer overlay & alignment check)
    pixel_geometry: Dict[str, Any] = field(default_factory=dict)

    # CAD World coordinates (calibrated real-world units, e.g. feet)
    cad_geometry: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "entity_type": self.entity_type.value,
            "layer": self.layer.value,
            "confidence": round(self.confidence, 3),
            "needs_review": self.needs_review,
            "source_evidence": self.source_evidence,
            "metadata": self.metadata,
            "pixel_geometry": self.pixel_geometry,
            "cad_geometry": self.cad_geometry,
        }


@dataclass
class CADLine(CADEntity):
    """Straight CAD Line entity."""
    start_px: Tuple[float, float] = (0.0, 0.0)
    end_px: Tuple[float, float] = (0.0, 0.0)
    start_cad: Tuple[float, float] = (0.0, 0.0)
    end_cad: Tuple[float, float] = (0.0, 0.0)

    def __post_init__(self):
        self.entity_type = EntityType.LINE
        self.pixel_geometry = {"start": self.start_px, "end": self.end_px}
        self.cad_geometry = {"start": self.start_cad, "end": self.end_cad}


@dataclass
class CADPolyline(CADEntity):
    """CAD LWPOLYLINE entity with optional closure."""
    points_px: List[Tuple[float, float]] = field(default_factory=list)
    points_cad: List[Tuple[float, float]] = field(default_factory=list)
    is_closed: bool = False

    def __post_init__(self):
        self.entity_type = EntityType.LWPOLYLINE
        self.pixel_geometry = {"points": self.points_px, "is_closed": self.is_closed}
        self.cad_geometry = {"points": self.points_cad, "is_closed": self.is_closed}


@dataclass
class CADArc(CADEntity):
    """CAD ARC entity (frequently used for door swings and curved walls)."""
    center_px: Tuple[float, float] = (0.0, 0.0)
    radius_px: float = 0.0
    center_cad: Tuple[float, float] = (0.0, 0.0)
    radius_cad: float = 0.0
    start_angle_deg: float = 0.0
    end_angle_deg: float = 90.0

    def __post_init__(self):
        self.entity_type = EntityType.ARC
        self.pixel_geometry = {
            "center": self.center_px,
            "radius": self.radius_px,
            "start_angle": self.start_angle_deg,
            "end_angle": self.end_angle_deg,
        }
        self.cad_geometry = {
            "center": self.center_cad,
            "radius": self.radius_cad,
            "start_angle": self.start_angle_deg,
            "end_angle": self.end_angle_deg,
        }


@dataclass
class CADHatch(CADEntity):
    """Native CAD HATCH entity.
    Maintains closed boundary paths (outer perimeter + internal hole paths).
    """
    pattern_name: str = "SOLID"  # SOLID, ANSI31, etc.
    # List of loops, where each loop is a list of (x, y) coordinates
    # Loop 0 is always the exterior boundary; Loop 1..n are holes/voids
    loops_px: List[List[Tuple[float, float]]] = field(default_factory=list)
    loops_cad: List[List[Tuple[float, float]]] = field(default_factory=list)
    associated_wall_ids: List[str] = field(default_factory=list)

    def __post_init__(self):
        self.entity_type = EntityType.HATCH
        self.layer = CADLayer.HATCH
        self.pixel_geometry = {
            "pattern": self.pattern_name,
            "loops": self.loops_px,
        }
        self.cad_geometry = {
            "pattern": self.pattern_name,
            "loops": self.loops_cad,
        }


@dataclass
class CADText(CADEntity):
    """Native CAD TEXT / MTEXT entity for labels, room names, and dimensions."""
    text_string: str = ""
    insert_px: Tuple[float, float] = (0.0, 0.0)
    insert_cad: Tuple[float, float] = (0.0, 0.0)
    height_px: float = 12.0
    height_cad: float = 0.5
    rotation_deg: float = 0.0
    bbox_px: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)

    def __post_init__(self):
        self.entity_type = EntityType.TEXT
        self.pixel_geometry = {
            "text": self.text_string,
            "insert": self.insert_px,
            "height": self.height_px,
            "rotation": self.rotation_deg,
            "bbox": self.bbox_px,
        }
        self.cad_geometry = {
            "text": self.text_string,
            "insert": self.insert_cad,
            "height": self.height_cad,
            "rotation": self.rotation_deg,
        }


@dataclass
class ReconstructedPlan:
    """Contains all reconstructed CAD entities, scale context, and diagnostics."""
    plan_name: str
    scale_context: Any  # ScaleContext
    entities: List[CADEntity] = field(default_factory=list)
    raster_width: int = 1000
    raster_height: int = 1000
    metadata: Dict[str, Any] = field(default_factory=dict)
    qa_report: Dict[str, Any] = field(default_factory=dict)

    def add_entity(self, entity: CADEntity):
        self.entities.append(entity)

    def get_by_layer(self, layer: CADLayer) -> List[CADEntity]:
        return [e for e in self.entities if e.layer == layer]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_name": self.plan_name,
            "scale": self.scale_context.to_dict() if hasattr(self.scale_context, "to_dict") else {},
            "raster_width": self.raster_width,
            "raster_height": self.raster_height,
            "entity_count": len(self.entities),
            "entities": [e.to_dict() for e in self.entities],
            "metadata": self.metadata,
            "qa_report": self.qa_report,
        }
