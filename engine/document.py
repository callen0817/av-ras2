"""AV Ras2 Document Intake Engine.

Supports loading raster and hybrid PDF, PNG, JPG, TIFF, BMP, and SVG files.
Inspects documents for native vector paths vs raster content,
extracts high-resolution images, and manages page selections.
"""

from dataclasses import dataclass, field
import io
import os
from typing import Any, Dict, List, Optional, Tuple
import cv2
import fitz  # PyMuPDF
import numpy as np
from PIL import Image


@dataclass
class DocumentPage:
    page_number: int
    width_px: int
    height_px: int
    dpi: float
    has_native_vectors: bool = False
    vector_path_count: int = 0
    image_np: Optional[np.ndarray] = None
    thumbnail_png: Optional[bytes] = None
    text_blocks: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class DocumentIntakeResult:
    file_path: str
    file_name: str
    file_type: str
    page_count: int
    pages: List[DocumentPage] = field(default_factory=list)
    has_recoverable_vectors: bool = False
    notes: List[str] = field(default_factory=list)


class DocumentLoader:
    """Robust document intake for architectural plans."""

    @classmethod
    def load_document(cls, file_path: str, target_dpi: int = 200) -> DocumentIntakeResult:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        file_name = os.path.basename(file_path)
        ext = os.path.splitext(file_path)[1].lower()

        if ext == ".pdf":
            return cls._load_pdf(file_path, target_dpi=target_dpi)
        elif ext in [".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"]:
            return cls._load_image(file_path)
        else:
            raise ValueError(f"Unsupported file format: {ext}")

    @classmethod
    def _load_pdf(cls, file_path: str, target_dpi: int = 200) -> DocumentIntakeResult:
        doc = fitz.open(file_path)
        page_count = len(doc)
        pages = []
        any_vectors = False
        notes = []

        zoom = target_dpi / 72.0  # 72 is standard PDF point resolution
        mat = fitz.Matrix(zoom, zoom)

        for page_idx in range(page_count):
            page = doc[page_idx]
            drawings = page.get_drawings()
            has_vectors = len(drawings) > 10
            if has_vectors:
                any_vectors = True

            # Render page to high-res pixmap
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img_data = pix.tobytes("png")
            nparr = np.frombuffer(img_data, np.uint8)
            img_np = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            # Generate thumbnail
            thumb_pix = page.get_pixmap(matrix=fitz.Matrix(0.2, 0.2), alpha=False)
            thumb_bytes = thumb_pix.tobytes("png")

            # Extract native text blocks and bounding boxes
            raw_blocks = page.get_text("blocks")
            text_blocks = []
            for b in raw_blocks:
                if len(b) >= 7 and b[6] == 0:  # Text block
                    text_str = b[4].strip()
                    if text_str:
                        text_blocks.append({
                            "text": text_str,
                            "bbox_px": (b[0] * zoom, b[1] * zoom, b[2] * zoom, b[3] * zoom),
                            "bbox_pdf": (b[0], b[1], b[2], b[3]),
                            "height_px": max(10.0, (b[3] - b[1]) * zoom),
                        })

            doc_page = DocumentPage(
                page_number=page_idx + 1,
                width_px=pix.width,
                height_px=pix.height,
                dpi=target_dpi,
                has_native_vectors=has_vectors,
                vector_path_count=len(drawings),
                image_np=img_np,
                thumbnail_png=thumb_bytes,
                text_blocks=text_blocks,
            )
            pages.append(doc_page)

        if any_vectors:
            notes.append("Native vector geometry detected in PDF. Geometric inspection active.")
        else:
            notes.append("Raster floor plan detected. Full CAD reconstruction pipeline active.")

        doc.close()
        return DocumentIntakeResult(
            file_path=file_path,
            file_name=os.path.basename(file_path),
            file_type="PDF",
            page_count=page_count,
            pages=pages,
            has_recoverable_vectors=any_vectors,
            notes=notes,
        )

    @classmethod
    def _load_image(cls, file_path: str) -> DocumentIntakeResult:
        pil_img = Image.open(file_path)
        dpi_info = pil_img.info.get("dpi", (150.0, 150.0))
        dpi = float(dpi_info[0]) if isinstance(dpi_info, tuple) else 150.0
        if dpi < 50.0:
            dpi = 150.0

        # Convert to OpenCV BGR
        img_np = cv2.cvtColor(np.array(pil_img.convert("RGB")), cv2.COLOR_RGB2BGR)
        h, w = img_np.shape[:2]

        # Generate thumbnail
        thumb_img = pil_img.copy()
        thumb_img.thumbnail((300, 300))
        thumb_buf = io.BytesIO()
        thumb_img.save(thumb_buf, format="PNG")
        thumb_bytes = thumb_buf.getvalue()

        page = DocumentPage(
            page_number=1,
            width_px=w,
            height_px=h,
            dpi=dpi,
            has_native_vectors=False,
            vector_path_count=0,
            image_np=img_np,
            thumbnail_png=thumb_bytes,
        )

        return DocumentIntakeResult(
            file_path=file_path,
            file_name=os.path.basename(file_path),
            file_type=os.path.splitext(file_path)[1].upper().replace(".", ""),
            page_count=1,
            pages=[page],
            has_recoverable_vectors=False,
            notes=["Raster image loaded. Reconstructing architectural CAD geometry."],
        )
