"""Unit tests for CAD Topology Engine.

Tests endpoint snapping, collinear segment merging, and duplicate elimination.
"""

import unittest
from engine.scale import ScaleContext, Unit
from engine.topology import CADTopologyEngine
from engine.cad_entities import CADLine, CADLayer


class TestCADTopology(unittest.TestCase):
    def setUp(self):
        self.scale = ScaleContext(units_per_pixel=0.05, unit=Unit.FEET)
        self.engine = CADTopologyEngine(self.scale, snap_distance_px=3.0)

    def test_collinear_segment_merging(self):
        # Two collinear line segments along y=100 from x=0..50 and x=50..100
        l1 = CADLine(layer=CADLayer.WALL, start_px=(0.0, 100.0), end_px=(50.0, 100.0))
        l2 = CADLine(layer=CADLayer.WALL, start_px=(50.0, 100.0), end_px=(100.0, 100.0))

        cleaned = self.engine.clean_lines([l1, l2])
        self.assertEqual(len(cleaned), 1, "Expected collinear adjacent segments to merge into 1 line")
        merged = cleaned[0]
        self.assertAlmostEqual(merged.start_px[0], 0.0, places=1)
        self.assertAlmostEqual(merged.end_px[0], 100.0, places=1)

    def test_endpoint_snapping(self):
        # Two lines meeting with a tiny 1.5px gap
        l1 = CADLine(layer=CADLayer.WALL, start_px=(0.0, 0.0), end_px=(100.0, 0.0))
        l2 = CADLine(layer=CADLayer.WALL, start_px=(101.5, 0.0), end_px=(101.5, 100.0))

        cleaned = self.engine.clean_lines([l1, l2])
        self.assertEqual(len(cleaned), 2)
        # Check that the shared vertex snapped together
        p1_end = cleaned[0].end_px
        p2_start = cleaned[1].start_px
        self.assertAlmostEqual(p1_end[0], p2_start[0], places=1)
        self.assertAlmostEqual(p1_end[1], p2_start[1], places=1)

    def test_duplicate_removal(self):
        # Two identical overlapping lines (one forward, one reverse)
        l1 = CADLine(layer=CADLayer.WALL, start_px=(10.0, 10.0), end_px=(80.0, 10.0))
        l2 = CADLine(layer=CADLayer.WALL, start_px=(80.0, 10.0), end_px=(10.0, 10.0))

        cleaned = self.engine.clean_lines([l1, l2])
        self.assertEqual(len(cleaned), 1, "Duplicate reverse line must be eliminated")


if __name__ == "__main__":
    unittest.main()
