"""AV Ras2 Raster Preprocessing Pipeline.

Provides grayscale normalization, noise suppression, adaptive binarization,
stroke-width analysis via distance transform, and connected-component separation.
Preserves narrow door openings, wall thickness boundaries, and thin swing arcs.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import cv2
import numpy as np


@dataclass
class PreprocessedResult:
    gray: np.ndarray
    binary: np.ndarray               # Foreground = 255 (dark linework in drawing)
    distance_map: np.ndarray         # Euclidean distance transform (stroke width)
    connected_components: Tuple[int, np.ndarray, np.ndarray, np.ndarray]  # num_labels, labels, stats, centroids
    thin_lines_mask: np.ndarray      # Thin strokes (dimensions, door swings, glass)
    thick_regions_mask: np.ndarray   # Filled regions / solid walls / columns
    text_mask: np.ndarray            # Mask of text / annotations (excluded from linework)
    deskew_angle: float = 0.0


class RasterPreprocessor:
    """Non-destructive image preprocessing for architectural linework."""

    @classmethod
    def process(
        cls,
        image_bgr: np.ndarray,
        auto_deskew: bool = False,
        known_text_bboxes: Optional[List[Tuple[float, float, float, float]]] = None,
    ) -> PreprocessedResult:
        if len(image_bgr.shape) == 3:
            gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        else:
            gray = image_bgr.copy()

        h, w = gray.shape[:2]

        # Denoise gently to preserve fine door swing curves and text
        denoised = cv2.fastNlMeansDenoising(gray, h=5) if gray.shape[0] < 3000 else gray

        # Otsu thresholding for architectural drawings (where background is light)
        _, otsu_thresh = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        # Build text exclusion mask
        text_mask = np.zeros((h, w), dtype=np.uint8)

        if known_text_bboxes:
            for bbox in known_text_bboxes:
                x0, y0, x1, y1 = [int(round(v)) for v in bbox]
                # Add 3px margin around text
                x0 = max(0, x0 - 3)
                y0 = max(0, y0 - 3)
                x1 = min(w - 1, x1 + 3)
                y1 = min(h - 1, y1 + 3)
                cv2.rectangle(text_mask, (x0, y0), (x1, y1), 255, -1)
        else:
            # Fallback: Identify isolated text-like connected components
            num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(otsu_thresh, connectivity=8)
            for lbl in range(1, num_labels):
                bw = stats[lbl, cv2.CC_STAT_WIDTH]
                bh = stats[lbl, cv2.CC_STAT_HEIGHT]
                area = stats[lbl, cv2.CC_STAT_AREA]
                bx = stats[lbl, cv2.CC_STAT_LEFT]
                by = stats[lbl, cv2.CC_STAT_TOP]

                # Typical text glyphs: height 8-40px, width 4-80px, area < 600px
                if (8 <= bh <= 45) and (4 <= bw <= 120) and (area < 800):
                    cv2.rectangle(text_mask, (max(0, bx - 2), max(0, by - 2)), (min(w - 1, bx + bw + 2), min(h - 1, by + bh + 2)), 255, -1)

        # Linework binary with text regions safely masked out
        geom_binary = cv2.bitwise_and(otsu_thresh, cv2.bitwise_not(text_mask))

        # Distance transform to compute stroke width at every dark pixel
        dist_transform = cv2.distanceTransform(geom_binary, cv2.DIST_L2, 5)

        # Separate thin lines vs filled thick regions using distance map
        thick_regions = cv2.morphologyEx(
            geom_binary, 
            cv2.MORPH_OPEN, 
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        )
        
        # Thin lines are everything in geometry mask minus thick regions
        thin_lines = cv2.bitwise_and(geom_binary, cv2.bitwise_not(thick_regions))

        # Connected component analysis on geometry
        cc_result = cv2.connectedComponentsWithStats(geom_binary, connectivity=8)

        deskew_angle = 0.0
        if auto_deskew:
            deskew_angle = cls.detect_skew(geom_binary)

        return PreprocessedResult(
            gray=denoised,
            binary=geom_binary,
            distance_map=dist_transform,
            connected_components=cc_result,
            thin_lines_mask=thin_lines,
            thick_regions_mask=thick_regions,
            text_mask=text_mask,
            deskew_angle=deskew_angle,
        )

    @classmethod
    def detect_skew(cls, binary_img: np.ndarray) -> float:
        """Detect small rotational skew from dominant architectural lines."""
        lines = cv2.HoughLinesP(binary_img, 1, np.pi / 180, threshold=120, minLineLength=100, maxLineGap=10)
        if lines is None:
            return 0.0

        angles = []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
            # Normalize to [-45, 45]
            if angle < -45:
                angle += 90
            elif angle > 45:
                angle -= 90
            if abs(angle) < 15:  # Only consider subtle skews
                angles.append(angle)

        if not angles:
            return 0.0
        median_angle = float(np.median(angles))
        return round(median_angle, 2)
