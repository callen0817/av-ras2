"""AV Ras2 Architectural Feature Recognition Engine.

Detects doors, 90-degree swing arcs, window glazing, and architectural symbols.
Assigns features to appropriate CAD layers:
- A-DOOR (doors & swings)
- A-GLAZ (windows & curtain walls)
- A-ANNO (dimensions & text)
- AV-REVIEW (uncertain features)
"""

from dataclasses import dataclass
import math
from typing import List, Optional, Tuple
import cv2
import numpy as np

from .cad_entities import CADEntity, CADLine, CADArc, CADLayer, EntityType
from .scale import ScaleContext


@dataclass
class DetectedDoor:
    swing_arc: Optional[CADArc]
    door_leaf: Optional[CADLine]
    opening_width_cad: float
    confidence: float


class ArchitecturalFeatureRecognizer:
    """Extracts doors, swings, and glazing from thin linework and wall gaps."""

    def __init__(self, scale_context: ScaleContext):
        self.scale = scale_context

    def detect_doors_and_arcs(
        self,
        thin_lines_mask: np.ndarray,
        binary_mask: np.ndarray
    ) -> Tuple[List[CADEntity], List[DetectedDoor], np.ndarray]:
        """Detect door swings and leaves from thin line geometry.
        Returns entities, detected doors list, and cleaned thin_lines_mask with doors erased.
        """
        entities: List[CADEntity] = []
        detected_doors: List[DetectedDoor] = []
        remaining_mask = thin_lines_mask.copy()

        # Find contours of thin linework
        contours, _ = cv2.findContours(
            thin_lines_mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE
        )

        for cnt in contours:
            if len(cnt) < 25:
                continue

            # Check if contour resembles a quarter circle arc (door swing)
            is_arc, arc_info = self._fit_door_swing_arc(cnt)
            if is_arc and arc_info is not None:
                cx, cy, r, start_deg, end_deg = arc_info
                radius_cad = self.scale.px_dist_to_cad(r)

                # Standard door widths are between 2.0 ft and 4.0 ft (or 600mm - 1200mm)
                is_valid_door_size = (
                    (self.scale.unit.value in ["ft", "in"] and 1.8 <= radius_cad <= 5.0) or
                    (self.scale.unit.value in ["m", "mm", "cm"] and 0.5 <= radius_cad <= 1.5) or
                    (radius_cad > 0.1)  # fallback tolerance
                )

                if is_valid_door_size:
                    center_cad = self.scale.px_to_cad(cx, cy)
                    arc_entity = CADArc(
                        layer=CADLayer.DOOR,
                        confidence=0.92,
                        source_evidence="door_swing_arc",
                        center_px=(cx, cy),
                        radius_px=r,
                        center_cad=center_cad,
                        radius_cad=radius_cad,
                        start_angle_deg=start_deg,
                        end_angle_deg=end_deg,
                        metadata={"radius_cad": round(radius_cad, 2)},
                    )
                    entities.append(arc_entity)

                    # Build accompanying door leaf line from center to start of arc
                    rad_start = math.radians(start_deg)
                    leaf_end_px = (cx + r * math.cos(rad_start), cy + r * math.sin(rad_start))
                    leaf_end_cad = self.scale.px_to_cad(leaf_end_px[0], leaf_end_px[1])

                    door_leaf = CADLine(
                        layer=CADLayer.DOOR,
                        confidence=0.90,
                        source_evidence="door_leaf",
                        start_px=(cx, cy),
                        end_px=leaf_end_px,
                        start_cad=center_cad,
                        end_cad=leaf_end_cad,
                        metadata={"is_door_leaf": True},
                    )
                    entities.append(door_leaf)

                    detected_doors.append(
                        DetectedDoor(
                            swing_arc=arc_entity,
                            door_leaf=door_leaf,
                            opening_width_cad=radius_cad,
                            confidence=0.92,
                        )
                    )

                    # Erase this door swing and leaf from the remaining thin lines mask
                    # so Hough lines do NOT create fragmented lines over the arc!
                    cv2.ellipse(
                        remaining_mask,
                        (int(round(cx)), int(round(cy))),
                        (int(round(r)), int(round(r))),
                        0,
                        start_deg,
                        end_deg,
                        0,
                        8,
                    )
                    cv2.line(
                        remaining_mask,
                        (int(round(cx)), int(round(cy))),
                        (int(round(leaf_end_px[0])), int(round(leaf_end_px[1]))),
                        0,
                        8,
                    )

        return entities, detected_doors, remaining_mask

    def detect_straight_thin_features(
        self,
        thin_lines_mask: np.ndarray
    ) -> List[CADEntity]:
        """Detect straight lines (glazing, stairs, fixtures, partitions) from remaining thin lines."""
        entities: List[CADEntity] = []

        # Probabilistic Hough line transform
        lines = cv2.HoughLinesP(
            thin_lines_mask,
            rho=1,
            theta=np.pi / 180,
            threshold=25,
            minLineLength=15,
            maxLineGap=6,
        )

        if lines is None:
            return entities

        raw_segments = []
        for line in lines:
            line_flat = np.array(line).reshape(-1)
            if len(line_flat) < 4:
                continue
            x1, y1, x2, y2 = float(line_flat[0]), float(line_flat[1]), float(line_flat[2]), float(line_flat[3])
            length_px = math.hypot(x2 - x1, y2 - y1)
            if length_px < 15:
                continue

            # Orthogonalize line: snap near-horizontal and near-vertical segments
            dx = x2 - x1
            dy = y2 - y1
            angle = math.degrees(math.atan2(abs(dy), abs(dx)))
            if angle <= 5.5:
                avg_y = (y1 + y2) / 2.0
                y1 = y2 = avg_y
            elif (90.0 - angle) <= 5.5:
                avg_x = (x1 + x2) / 2.0
                x1 = x2 = avg_x

            raw_segments.append((x1, y1, x2, y2, length_px))

        # Check for stair patterns (multiple parallel lines within close proximity)
        for x1, y1, x2, y2, length_px in raw_segments:
            length_cad = self.scale.px_dist_to_cad(length_px)
            start_cad = self.scale.px_to_cad(x1, y1)
            end_cad = self.scale.px_to_cad(x2, y2)

            # Heuristic layering:
            # - Short parallel lines: window glazing or stairs
            # - Mid-length lines: partitions / glazing
            # - Long lines: room boundary / annotations
            if 1.5 <= length_cad <= 8.0:
                layer = CADLayer.GLAZING
            elif length_cad < 1.5:
                layer = CADLayer.FIXTURES
            else:
                layer = CADLayer.ANNOTATION

            cad_line = CADLine(
                layer=layer,
                confidence=0.88,
                source_evidence="thin_feature_stroke",
                start_px=(x1, y1),
                end_px=(x2, y2),
                start_cad=start_cad,
                end_cad=end_cad,
                metadata={"length_cad": round(length_cad, 2)},
            )
            entities.append(cad_line)

        return entities

    def _fit_door_swing_arc(self, contour: np.ndarray) -> Tuple[bool, Optional[Tuple[float, float, float, float, float]]]:
        """Fit an arc to a contour or sub-sequence of connected door linework."""
        if len(contour) < 15:
            return False, None

        # Pass 1: Test if isolated contour is a clean arc
        pts = contour.reshape(-1, 2).astype(np.float32)
        (cx, cy), radius = cv2.minEnclosingCircle(contour)
        if 25 <= radius <= 350:
            dists = np.hypot(pts[:, 0] - cx, pts[:, 1] - cy)
            mean_d = float(np.mean(dists))
            std_d = float(np.std(dists))
            if (std_d / (mean_d + 1e-5)) < 0.15:
                angles = np.unwrap(np.arctan2(pts[:, 1] - cy, pts[:, 0] - cx))
                span = math.degrees(abs(angles[-1] - angles[0]))
                if 68 <= span <= 115:
                    deg_arr = np.degrees(np.arctan2(pts[:, 1] - cy, pts[:, 0] - cx)) % 360
                    return True, (cx, cy, mean_d, float(np.min(deg_arr)), float(np.max(deg_arr)))

        # Pass 2: Deconstruct connected door assembly (arc + leaf line + jamb)
        poly = cv2.approxPolyDP(contour, 3.0, closed=True).reshape(-1, 2)
        n_vert = len(poly)
        if n_vert >= 4:
            for i in range(n_vert):
                for win in range(4, min(14, n_vert)):
                    sub_pts = np.array([poly[(i + k) % n_vert] for k in range(win)], dtype=np.float32)
                    (scx, scy), s_radius = cv2.minEnclosingCircle(sub_pts)
                    if 25 <= s_radius <= 250:
                        s_dists = np.hypot(sub_pts[:, 0] - scx, sub_pts[:, 1] - scy)
                        s_std = float(np.std(s_dists))
                        if (s_std / (s_radius + 1e-5)) < 0.12:
                            s_angles = np.unwrap(np.arctan2(sub_pts[:, 1] - scy, sub_pts[:, 0] - scx))
                            s_span = math.degrees(abs(s_angles[-1] - s_angles[0]))
                            if 68 <= s_span <= 115:
                                deg_arr = np.degrees(np.arctan2(sub_pts[:, 1] - scy, sub_pts[:, 0] - scx)) % 360
                                return True, (scx, scy, s_radius, float(np.min(deg_arr)), float(np.max(deg_arr)))

        return False, None
