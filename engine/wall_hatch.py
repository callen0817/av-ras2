"""AV Ras2 Wall & Hatch Intelligence Engine.

CRITICAL ARCHITECTURAL RECONSTRUCTION ENGINE:
Distinguishes graphic strokes from filled architectural regions.
Reconstructs solid black wall cuts (poche) into:
1. Independent editable wall boundary lines (Layer: A-WALL)
2. Native CAD HATCH entity enclosing the region (Layer: A-HATCH)
3. Preserves openings, wall junctions (L, T, cross), and column cuts (Layer: A-COLS)
"""

from dataclasses import dataclass, field
import math
from typing import Dict, List, Optional, Tuple
import cv2
import numpy as np
from shapely.geometry import Polygon, MultiPolygon, LineString, box
from shapely.ops import polygonize, unary_union

from .cad_entities import CADEntity, CADLine, CADPolyline, CADArc, CADHatch, CADLayer, EntityType
from .scale import ScaleContext


@dataclass
class ReconstructedWall:
    boundary_entities: List[CADEntity]
    hatch_entity: CADHatch
    thickness_px: float
    thickness_cad: float
    is_column: bool = False
    confidence: float = 0.95


class WallHatchIntelligence:
    """Classifies raster fills and reconstructs independent boundaries & hatches."""

    def __init__(self, scale_context: ScaleContext):
        self.scale = scale_context

    def reconstruct_from_masks(
        self,
        binary_drawing: np.ndarray,
        thick_regions_mask: np.ndarray,
        distance_map: np.ndarray,
    ) -> List[ReconstructedWall]:
        """Process thick filled regions and reconstruct them into CAD walls and hatches."""
        reconstructed_walls: List[ReconstructedWall] = []

        # Find contours of filled regions (both exterior boundary and interior courtyard/room holes)
        contours, hierarchy = cv2.findContours(
            thick_regions_mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE
        )

        if not contours or hierarchy is None:
            return reconstructed_walls

        h_info = hierarchy[0]

        for i, cnt in enumerate(contours):
            # Only process parent / external contours first
            if h_info[i][3] != -1:
                continue

            area = cv2.contourArea(cnt)
            # Filter tiny speckle noise (< 80 px)
            if area < 80:
                continue

            # Check if this contour has child holes (internal rooms or voids)
            child_contours = []
            child_idx = h_info[i][2]
            while child_idx != -1:
                child_cnt = contours[child_idx]
                if cv2.contourArea(child_cnt) > 40:
                    child_contours.append(child_cnt)
                child_idx = h_info[child_idx][0]

            # Reconstruct this filled poche region
            wall = self._reconstruct_single_region(
                external_cnt=cnt,
                hole_cnts=child_contours,
                distance_map=distance_map,
            )
            if wall:
                reconstructed_walls.append(wall)

        return reconstructed_walls

    def _reconstruct_single_region(
        self,
        external_cnt: np.ndarray,
        hole_cnts: List[np.ndarray],
        distance_map: np.ndarray,
    ) -> Optional[ReconstructedWall]:
        """Convert a single filled contour into editable boundaries and a native CAD hatch."""
        # Simplify contour to clean orthogonal / architectural polygon vertices
        epsilon = 2.0
        poly_ext = cv2.approxPolyDP(external_cnt, epsilon, closed=True)
        if len(poly_ext) < 3:
            return None

        raw_ext_pts = [(float(pt[0][0]), float(pt[0][1])) for pt in poly_ext]
        ext_pts_px = self.rectify_orthogonal_polygon(raw_ext_pts)

        # Simplify hole contours
        hole_pts_px_list = []
        for h_cnt in hole_cnts:
            poly_h = cv2.approxPolyDP(h_cnt, epsilon, closed=True)
            if len(poly_h) >= 3:
                raw_h_pts = [(float(pt[0][0]), float(pt[0][1])) for pt in poly_h]
                hole_pts_px_list.append(self.rectify_orthogonal_polygon(raw_h_pts))

        # Calculate region properties
        bx, by, bw, bh = cv2.boundingRect(external_cnt)
        aspect = max(bw, bh) / max(1, min(bw, bh))
        area = cv2.contourArea(external_cnt)
        bbox_area = float(bw * bh)
        solidity = area / max(1.0, bbox_area)

        # Estimate wall thickness from distance transform peak (ridge radius * 2)
        mask = np.zeros(distance_map.shape, dtype=np.uint8)
        cv2.drawContours(mask, [external_cnt], -1, 255, -1)
        _, max_val, _, _ = cv2.minMaxLoc(distance_map, mask=mask)
        est_thickness_px = max(2.0, max_val * 2.0)
        est_thickness_cad = self.scale.px_dist_to_cad(est_thickness_px)

        bw_cad = self.scale.px_dist_to_cad(float(bw))
        bh_cad = self.scale.px_dist_to_cad(float(bh))

        # Column vs Wall detection:
        # A structural column is compact in physical size (<= 3.5 ft / ~1m), has high solidity (>= 0.75),
        # and balanced aspect ratio. An L-wall or wall network has low solidity (< 0.6) or large extent.
        is_column = (
            (solidity >= 0.70)
            and (aspect < 1.6)
            and (bw_cad <= 3.5)
            and (bh_cad <= 3.5)
            and (min(bw, bh) >= 8)
        )

        # Generate CAD coordinates for the hatch boundary loops
        ext_loop_cad = [self.scale.px_to_cad(x, y) for (x, y) in ext_pts_px]
        hole_loops_cad = [
            [self.scale.px_to_cad(x, y) for (x, y) in h_pts]
            for h_pts in hole_pts_px_list
        ]

        all_loops_px = [ext_pts_px] + hole_pts_px_list
        all_loops_cad = [ext_loop_cad] + hole_loops_cad

        layer_target = CADLayer.COLUMNS if is_column else CADLayer.WALL

        # Build independent boundary line entities
        boundary_entities: List[CADEntity] = []

        # If it's a simple rectangular wall segment (4 vertices), we separate it explicitly
        # into Two Wall Boundaries (long sides) and two end caps/openings (short sides)
        if len(ext_pts_px) == 4 and not hole_pts_px_list and not is_column:
            edges = []
            for j in range(4):
                p_start = ext_pts_px[j]
                p_end = ext_pts_px[(j + 1) % 4]
                length = math.hypot(p_end[0] - p_start[0], p_end[1] - p_start[1])
                edges.append((p_start, p_end, length, j))

            # Sort edges by length
            edges.sort(key=lambda e: e[2], reverse=True)
            # Longest 2 edges are the two independent wall boundaries
            wall_boundaries = edges[:2]
            # Short edges are end caps/openings
            end_caps = edges[2:]

            for idx, (p_start, p_end, _, _) in enumerate(wall_boundaries):
                line = CADLine(
                    layer=CADLayer.WALL,
                    confidence=0.98,
                    source_evidence=f"wall_boundary_side_{idx+1}",
                    start_px=p_start,
                    end_px=p_end,
                    start_cad=self.scale.px_to_cad(p_start[0], p_start[1]),
                    end_cad=self.scale.px_to_cad(p_end[0], p_end[1]),
                    metadata={
                        "boundary_index": idx + 1,
                        "wall_thickness_cad": round(est_thickness_cad, 3),
                        "wall_thickness_px": round(est_thickness_px, 1),
                    },
                )
                boundary_entities.append(line)

            # Add end caps as distinct closing lines on A-WALL
            for p_start, p_end, _, _ in end_caps:
                line = CADLine(
                    layer=CADLayer.WALL,
                    confidence=0.95,
                    source_evidence="wall_end_cap",
                    start_px=p_start,
                    end_px=p_end,
                    start_cad=self.scale.px_to_cad(p_start[0], p_start[1]),
                    end_cad=self.scale.px_to_cad(p_end[0], p_end[1]),
                    metadata={"is_end_cap": True},
                )
                boundary_entities.append(line)

        else:
            # Complex wall network (L-shaped, T-junction, multi-room loop):
            # Deconstruct the outer boundary loop and hole loops into continuous clean
            # boundary polyline/line segments so each wall face is independently selectable!
            for loop_idx, (pts_px, pts_cad) in enumerate(zip(all_loops_px, all_loops_cad)):
                poly_entity = CADPolyline(
                    layer=layer_target,
                    confidence=0.96,
                    source_evidence="column_boundary" if is_column else f"wall_boundary_loop_{loop_idx}",
                    points_px=pts_px,
                    points_cad=pts_cad,
                    is_closed=True,
                    metadata={
                        "is_loop": True,
                        "loop_type": "exterior" if loop_idx == 0 else "interior_void",
                        "wall_thickness_cad": round(est_thickness_cad, 3),
                    },
                )
                boundary_entities.append(poly_entity)

        # Build native CAD HATCH entity enclosing the region
        hatch_entity = CADHatch(
            layer=CADLayer.HATCH,
            confidence=0.99,
            source_evidence="wall_poche_fill",
            pattern_name="SOLID",
            loops_px=all_loops_px,
            loops_cad=all_loops_cad,
            associated_wall_ids=[e.id for e in boundary_entities],
            metadata={
                "area_cad": round(self.scale.px_dist_to_cad(math.sqrt(area)) ** 2, 3),
                "is_column_hatch": is_column,
                "wall_thickness_cad": round(est_thickness_cad, 3),
            },
        )

        return ReconstructedWall(
            boundary_entities=boundary_entities,
            hatch_entity=hatch_entity,
            thickness_px=est_thickness_px,
            thickness_cad=est_thickness_cad,
            is_column=is_column,
            confidence=0.95,
        )

    @staticmethod
    def rectify_orthogonal_polygon(pts: List[Tuple[float, float]], angle_tol_deg: float = 6.0) -> List[Tuple[float, float]]:
        """Snap near-horizontal and near-vertical polygon segments to strict 0° / 90°
        and remove collinear redundant vertices along straight walls."""
        if len(pts) < 3:
            return pts

        n = len(pts)
        rectified = list(pts)

        # Pass 1: Snap consecutive edge orientations
        for i in range(n):
            p1 = rectified[i]
            p2 = rectified[(i + 1) % n]
            dx = p2[0] - p1[0]
            dy = p2[1] - p1[1]
            dist = math.hypot(dx, dy)
            if dist < 1e-3:
                continue

            angle = math.degrees(math.atan2(abs(dy), abs(dx)))
            # If within angle_tol_deg of horizontal (0 deg)
            if angle <= angle_tol_deg:
                avg_y = (p1[1] + p2[1]) / 2.0
                rectified[i] = (p1[0], avg_y)
                rectified[(i + 1) % n] = (p2[0], avg_y)
            # If within angle_tol_deg of vertical (90 deg)
            elif (90.0 - angle) <= angle_tol_deg:
                avg_x = (p1[0] + p2[0]) / 2.0
                rectified[i] = (avg_x, p1[1])
                rectified[(i + 1) % n] = (avg_x, p2[1])

        # Pass 2: Merge collinear vertices
        clean = []
        for i in range(len(rectified)):
            p_prev = rectified[(i - 1) % len(rectified)]
            p_curr = rectified[i]
            p_next = rectified[(i + 1) % len(rectified)]

            v1 = (p_curr[0] - p_prev[0], p_curr[1] - p_prev[1])
            v2 = (p_next[0] - p_curr[0], p_next[1] - p_curr[1])
            d1 = math.hypot(v1[0], v1[1])
            d2 = math.hypot(v2[0], v2[1])

            if d1 > 1e-3 and d2 > 1e-3:
                cross = abs(v1[0] * v2[1] - v1[1] * v2[0]) / (d1 * d2)
                dot = (v1[0] * v2[0] + v1[1] * v2[1]) / (d1 * d2)
                if cross < 0.05 and dot > 0.95:
                    continue  # skip collinear intermediate vertex

            clean.append(p_curr)

        return clean if len(clean) >= 3 else rectified
