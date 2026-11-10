"""Unit tests for Scale Intelligence Engine."""

import math
import unittest
import numpy as np
from engine.scale import ScaleEngine, ScaleContext, Unit


class TestScaleEngine(unittest.TestCase):
    def test_two_point_calibration(self):
        # 200 pixels equals 10.0 feet -> 0.05 feet per pixel
        p1 = (100.0, 100.0)
        p2 = (300.0, 100.0)
        ctx = ScaleEngine.calibrate_from_two_points(p1, p2, 10.0, Unit.FEET, 1000.0, 1000.0)

        self.assertAlmostEqual(ctx.units_per_pixel, 0.05, places=4)
        self.assertEqual(ctx.unit, Unit.FEET)

        # Test coordinate transformation (Y is inverted for CAD upright modelspace)
        cad_x, cad_y = ctx.px_to_cad(100.0, 1000.0)
        self.assertAlmostEqual(cad_x, 5.0, places=3)
        self.assertAlmostEqual(cad_y, 0.0, places=3)

        # Test round trip px -> cad -> px
        px_back, py_back = ctx.cad_to_px(cad_x, cad_y)
        self.assertAlmostEqual(px_back, 100.0, places=3)
        self.assertAlmostEqual(py_back, 1000.0, places=3)

    def test_multi_reference_residual_error(self):
        refs = [
            ((0.0, 0.0), (100.0, 0.0), 5.0),    # 0.05
            ((0.0, 0.0), (200.0, 0.0), 10.0),   # 0.05
            ((0.0, 0.0), (400.0, 0.0), 20.0),   # 0.05
        ]
        ctx = ScaleEngine.calibrate_from_multiple_references(refs, Unit.FEET)
        self.assertAlmostEqual(ctx.units_per_pixel, 0.05, places=4)
        self.assertLess(ctx.residual_error, 1e-4)

    def test_matterport_scale_bar_detection(self):
        img = np.full((1200, 1200, 3), 255, dtype=np.uint8)
        # Draw horizontal scale bar: 200px long, 10px high at (100, 1100)
        img[1100:1110, 100:300] = 0

        ctx = ScaleEngine.detect_matterport_scale_bar(img)
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx.method, "matterport_scale_bar")
        self.assertAlmostEqual(ctx.units_per_pixel, 0.05, places=2)


if __name__ == "__main__":
    unittest.main()
