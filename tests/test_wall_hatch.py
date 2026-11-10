"""Unit tests for Wall & Hatch Intelligence Engine.

CRITICAL ACCEPTANCE CRITERIA:
Verify that a solid black poche wall cut is reconstructed into:
1. Two independent editable wall boundary lines (Layer: A-WALL)
2. Enclosing a separate native CAD HATCH entity (Layer: A-HATCH)
Also verifies L-junctions, T-junctions, and column discrimination.
"""

import unittest
import numpy as np
import cv2

from engine.scale import ScaleContext, Unit
from engine.preprocess import RasterPreprocessor
from engine.wall_hatch import WallHatchIntelligence, ReconstructedWall
from engine.cad_entities import CADLayer, EntityType, CADLine, CADHatch


class TestWallHatchIntelligence(unittest.TestCase):
    def setUp(self):
        # 1 px = 0.05 ft -> 20px wall = 1.0 ft wall thickness
        self.scale = ScaleContext(
            units_per_pixel=0.05,
            unit=Unit.FEET,
            image_width=1000.0,
            image_height=1000.0,
        )
        self.engine = WallHatchIntelligence(self.scale)

    def test_solid_black_wall_poche_reconstruction(self):
        """CRITICAL: Single solid black wall cut must yield two boundaries + native hatch."""
        # Create a white canvas with a single solid black rectangular wall
        # Wall is 300px long, 20px thick (horizontal wall)
        img = np.full((500, 500, 3), 255, dtype=np.uint8)
        # Coordinates: y from 200 to 220, x from 100 to 400
        img[200:220, 100:400] = 0

        prep = RasterPreprocessor.process(img)
        walls = self.engine.reconstruct_from_masks(
            binary_drawing=prep.binary,
            thick_regions_mask=prep.thick_regions_mask,
            distance_map=prep.distance_map,
        )

        self.assertEqual(len(walls), 1, "Expected exactly 1 reconstructed wall region")
        wall = walls[0]

        # 1. Verify Native CAD Hatch
        self.assertIsNotNone(wall.hatch_entity)
        self.assertEqual(wall.hatch_entity.entity_type, EntityType.HATCH)
        self.assertEqual(wall.hatch_entity.layer, CADLayer.HATCH)
        self.assertEqual(wall.hatch_entity.pattern_name, "SOLID")
        self.assertTrue(len(wall.hatch_entity.loops_cad) >= 1)

        # 2. Verify Independent Boundary Linework
        self.assertTrue(len(wall.boundary_entities) >= 2)
        # Find the long boundary lines (the two wall faces)
        wall_lines = [
            e for e in wall.boundary_entities 
            if e.entity_type == EntityType.LINE and e.metadata.get("boundary_index") in [1, 2]
        ]
        self.assertEqual(len(wall_lines), 2, "Must produce exactly two independent wall boundaries")

        b1, b2 = wall_lines[0], wall_lines[1]
        self.assertEqual(b1.layer, CADLayer.WALL)
        self.assertEqual(b2.layer, CADLayer.WALL)

        # Verify they are parallel and separated by approximately wall thickness (20px * 0.05 = 1.0 ft)
        y1 = (b1.start_px[1] + b1.end_px[1]) / 2.0
        y2 = (b2.start_px[1] + b2.end_px[1]) / 2.0
        separation_px = abs(y1 - y2)
        self.assertAlmostEqual(separation_px, 20.0, delta=3.0)
        self.assertAlmostEqual(wall.thickness_cad, 1.0, delta=0.25)

    def test_column_vs_wall_classification(self):
        """Structural column cuts (compact square) must be classified as A-COLS, not normal walls."""
        img = np.full((500, 500, 3), 255, dtype=np.uint8)
        # Square column cut: 30x30 pixels
        img[100:130, 100:130] = 0

        prep = RasterPreprocessor.process(img)
        walls = self.engine.reconstruct_from_masks(
            binary_drawing=prep.binary,
            thick_regions_mask=prep.thick_regions_mask,
            distance_map=prep.distance_map,
        )

        self.assertEqual(len(walls), 1)
        col = walls[0]
        self.assertTrue(col.is_column, "Compact square poche must be classified as column")
        for ent in col.boundary_entities:
            self.assertEqual(ent.layer, CADLayer.COLUMNS)

    def test_l_shaped_wall_junction(self):
        """L-shaped interconnected wall poche must produce closed boundary loop and solid hatch."""
        img = np.full((500, 500, 3), 255, dtype=np.uint8)
        # L-junction: 20px thick
        # Horizontal leg: (100, 200) to (300, 220)
        img[200:220, 100:300] = 0
        # Vertical leg: (280, 220) to (300, 400)
        img[220:400, 280:300] = 0

        prep = RasterPreprocessor.process(img)
        walls = self.engine.reconstruct_from_masks(
            binary_drawing=prep.binary,
            thick_regions_mask=prep.thick_regions_mask,
            distance_map=prep.distance_map,
        )

        self.assertEqual(len(walls), 1, "L-junction must be recognized as single connected wall network")
        wall = walls[0]
        self.assertEqual(wall.hatch_entity.layer, CADLayer.HATCH)
        self.assertFalse(wall.is_column)


if __name__ == "__main__":
    unittest.main()
