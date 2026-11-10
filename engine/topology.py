"""AV Ras2 CAD Topology & Geometric Cleanup Engine.

Performs collinear line merging, endpoint snapping, orthogonal snapping
within evidence bounds, duplicate elimination, and intersection cleanup.
"""

import math
from typing import List, Optional, Tuple
import numpy as np

from .cad_entities import CADEntity, CADLine, CADPolyline, CADArc, CADLayer, EntityType
from .scale import ScaleContext


class CADTopologyEngine:
    """Cleans and validates CAD geometry."""

    def __init__(self, scale_context: ScaleContext, snap_distance_px: float = 3.0):
        self.scale = scale_context
        self.snap_distance_px = snap_distance_px

    def clean_lines(self, lines: List[CADLine]) -> List[CADLine]:
        """Snap endpoints, merge collinear lines, and remove duplicates."""
        if not lines:
            return []

        # Step 1: Remove micro segments (< 2.0 pixels)
        filtered = [l for l in lines if self._line_length_px(l) >= 2.0]

        # Step 2: Strictly rectify orthogonal lines (prevent slight angles on straight walls)
        rectified = [self._snap_orthogonal_line(l) for l in filtered]

        # Step 3: Snap close endpoints together
        snapped = self._snap_endpoints(rectified)

        # Step 4: Merge collinear adjacent segments
        merged = self._merge_collinear_lines(snapped)

        # Step 5: Remove duplicate / reverse overlapping lines
        unique = self._remove_duplicates(merged)

        return unique

    def _snap_orthogonal_line(self, line: CADLine, angle_tol_deg: float = 5.0) -> CADLine:
        """Snap near-horizontal and near-vertical lines to strict 0° or 90°."""
        dx = line.end_px[0] - line.start_px[0]
        dy = line.end_px[1] - line.start_px[1]
        dist = math.hypot(dx, dy)
        if dist < 1e-3:
            return line

        angle = math.degrees(math.atan2(abs(dy), abs(dx)))
        s_px = list(line.start_px)
        e_px = list(line.end_px)

        if angle <= angle_tol_deg:
            # Strictly horizontal line
            avg_y = (s_px[1] + e_px[1]) / 2.0
            s_px[1] = avg_y
            e_px[1] = avg_y
        elif (90.0 - angle) <= angle_tol_deg:
            # Strictly vertical line
            avg_x = (s_px[0] + e_px[0]) / 2.0
            s_px[0] = avg_x
            e_px[0] = avg_x

        s_cad = self.scale.px_to_cad(s_px[0], s_px[1])
        e_cad = self.scale.px_to_cad(e_px[0], e_px[1])

        # Enforce exact matching coordinate in CAD world space
        if s_px[1] == e_px[1]:
            s_cad = (s_cad[0], round((s_cad[1] + e_cad[1]) / 2.0, 4))
            e_cad = (e_cad[0], s_cad[1])
        elif s_px[0] == e_px[0]:
            s_cad = (round((s_cad[0] + e_cad[0]) / 2.0, 4), s_cad[1])
            e_cad = (s_cad[0], e_cad[1])

        return CADLine(
            id=line.id,
            layer=line.layer,
            confidence=line.confidence,
            source_evidence=line.source_evidence,
            start_px=(s_px[0], s_px[1]),
            end_px=(e_px[0], e_px[1]),
            start_cad=s_cad,
            end_cad=e_cad,
            metadata=line.metadata,
        )

    def _line_length_px(self, line: CADLine) -> float:
        return math.hypot(line.end_px[0] - line.start_px[0], line.end_px[1] - line.start_px[1])

    def _snap_endpoints(self, lines: List[CADLine]) -> List[CADLine]:
        """Cluster and snap endpoints within snap tolerance."""
        points: List[Tuple[float, float]] = []
        for l in lines:
            points.append(l.start_px)
            points.append(l.end_px)

        # Cluster points
        snapped_pts = list(points)
        n = len(points)
        for i in range(n):
            for j in range(i + 1, n):
                d = math.hypot(points[i][0] - points[j][0], points[i][1] - points[j][1])
                if d <= self.snap_distance_px:
                    mid_x = (points[i][0] + points[j][0]) / 2.0
                    mid_y = (points[i][1] + points[j][1]) / 2.0
                    snapped_pts[i] = (mid_x, mid_y)
                    snapped_pts[j] = (mid_x, mid_y)

        result = []
        for idx, l in enumerate(lines):
            s_px = snapped_pts[idx * 2]
            e_px = snapped_pts[idx * 2 + 1]
            # Don't collapse line to point
            if math.hypot(e_px[0] - s_px[0], e_px[1] - s_px[1]) < 1.0:
                continue

            s_cad = self.scale.px_to_cad(s_px[0], s_px[1])
            e_cad = self.scale.px_to_cad(e_px[0], e_px[1])

            nl = CADLine(
                id=l.id,
                layer=l.layer,
                confidence=l.confidence,
                source_evidence=l.source_evidence,
                start_px=s_px,
                end_px=e_px,
                start_cad=s_cad,
                end_cad=e_cad,
                metadata=l.metadata,
            )
            result.append(nl)

        return result

    def _merge_collinear_lines(self, lines: List[CADLine]) -> List[CADLine]:
        """Merge lines that share an endpoint and have identical angle."""
        if len(lines) <= 1:
            return lines

        merged = list(lines)
        changed = True
        max_passes = 5
        passes = 0

        while changed and passes < max_passes:
            changed = False
            passes += 1
            i = 0
            while i < len(merged):
                j = i + 1
                while j < len(merged):
                    l1 = merged[i]
                    l2 = merged[j]
                    if l1.layer == l2.layer:
                        combined = self._try_merge_two_lines(l1, l2)
                        if combined is not None:
                            merged[i] = combined
                            merged.pop(j)
                            changed = True
                            continue
                    j += 1
                i += 1

        return merged

    def _try_merge_two_lines(self, l1: CADLine, l2: CADLine) -> Optional[CADLine]:
        """Try to merge two lines if collinear and connected."""
        # Angle of l1 and l2
        ang1 = math.degrees(math.atan2(l1.end_px[1] - l1.start_px[1], l1.end_px[0] - l1.start_px[0])) % 180
        ang2 = math.degrees(math.atan2(l2.end_px[1] - l2.start_px[1], l2.end_px[0] - l2.start_px[0])) % 180

        diff = abs(ang1 - ang2)
        if diff > 180:
            diff = 360 - diff
        if diff > 3.0 and abs(diff - 180) > 3.0:
            return None  # Not collinear

        # Check for shared endpoint
        tol = self.snap_distance_px
        pairs = [
            (l1.end_px, l2.start_px, l1.start_px, l2.end_px),
            (l1.end_px, l2.end_px, l1.start_px, l2.start_px),
            (l1.start_px, l2.start_px, l1.end_px, l2.end_px),
            (l1.start_px, l2.end_px, l1.end_px, l2.start_px),
        ]

        for shared1, shared2, p_start, p_end in pairs:
            if math.hypot(shared1[0] - shared2[0], shared1[1] - shared2[1]) <= tol:
                return CADLine(
                    id=l1.id,
                    layer=l1.layer,
                    confidence=min(l1.confidence, l2.confidence),
                    source_evidence="collinear_merged",
                    start_px=p_start,
                    end_px=p_end,
                    start_cad=self.scale.px_to_cad(p_start[0], p_start[1]),
                    end_cad=self.scale.px_to_cad(p_end[0], p_end[1]),
                    metadata=l1.metadata,
                )
        return None

    def _remove_duplicates(self, lines: List[CADLine]) -> List[CADLine]:
        """Remove identical or reverse-identical lines."""
        unique: List[CADLine] = []
        for l in lines:
            is_dup = False
            for u in unique:
                d1 = math.hypot(l.start_px[0] - u.start_px[0], l.start_px[1] - u.start_px[1])
                d2 = math.hypot(l.end_px[0] - u.end_px[0], l.end_px[1] - u.end_px[1])
                if d1 < 2.0 and d2 < 2.0:
                    is_dup = True
                    break
                # Check reversed
                d1_rev = math.hypot(l.start_px[0] - u.end_px[0], l.start_px[1] - u.end_px[1])
                d2_rev = math.hypot(l.end_px[0] - u.start_px[0], l.end_px[1] - u.start_px[1])
                if d1_rev < 2.0 and d2_rev < 2.0:
                    is_dup = True
                    break
            if not is_dup:
                unique.append(l)
        return unique
