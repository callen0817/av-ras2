"""AV Ras2 - Intelligent Raster to CAD Reconstruction Engine.
Artificial Vision, Inc.
"""

from .scale import ScaleContext, ScaleEngine, Unit
from .document import DocumentLoader, DocumentPage, DocumentIntakeResult
from .preprocess import RasterPreprocessor, PreprocessedResult
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
from .wall_hatch import WallHatchIntelligence, ReconstructedWall
from .topology import CADTopologyEngine
from .architectural import ArchitecturalFeatureRecognizer
from .export_dxf import DXFExportEngine
from .export_svg import SVGExportEngine
from .export_pdf import PDFExportEngine
from .qa import CADQualityAssurance
from .pipeline import ConversionPipeline

__version__ = "1.0.0"
