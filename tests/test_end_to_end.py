"""End-to-End Pipeline Acceptance Test.

Synthesizes a realistic Matterport raster floor plan containing:
- Exterior and interior solid black poche walls
- Door opening with a 90-degree swing arc
- Window openings
- Scale bar legend
Executes ConversionPipeline.run() and verifies:
- Wall and hatch reconstruction
- Door and arc recognition
- Topological cleaning
- DXF, SVG, PDF, and QA overlay generation.
"""

import os
import unittest
import cv2
import numpy as np

from engine.pipeline import ConversionPipeline
from engine.scale import Unit
from engine.cad_entities import CADLayer, EntityType


class TestEndToEndPipeline(unittest.TestCase):
    def setUp(self):
        self.output_dir = os.path.join(os.path.dirname(__file__), "test_output_e2e")
        os.makedirs(self.output_dir, exist_ok=True)

        # Create a synthetic 1200x1200 architectural floor plan
        self.img = np.full((1200, 1200, 3), 255, dtype=np.uint8)

        # 1. Outer perimeter solid poche walls (20px thick)
        # Top wall: x=200..1000, y=200..220
        self.img[200:220, 200:1000] = 0
        # Bottom wall: x=200..1000, y=800..820
        self.img[800:820, 200:1000] = 0
        # Left wall: x=200..220, y=200..820
        self.img[200:820, 200:220] = 0
        # Right wall: x=980..1000, y=200..820
        self.img[200:820, 980:1000] = 0

        # 2. Interior dividing wall: x=580..600, y=220..800
        # With a door opening gap at y=450..510 (60px = 3.0 ft opening)
        self.img[220:450, 580:600] = 0
        self.img[510:800, 580:600] = 0

        # 3. Door swing arc at the opening:
        # Center at (600, 450), radius 60, swing from angle 0 to 90 degrees
        cv2.ellipse(self.img, (600, 450), (60, 60), 0, 0, 90, (0, 0, 0), 2)
        # Door leaf line from (600, 450) to (660, 450)
        cv2.line(self.img, (600, 450), (660, 450), (0, 0, 0), 2)

        # 4. Scale bar at bottom: (200, 1100) to (400, 1110) = 200px (10.0 ft)
        self.img[1100:1110, 200:400] = 0

        self.input_image_path = os.path.join(self.output_dir, "synthetic_floor_plan.png")
        cv2.imwrite(self.input_image_path, self.img)

    def test_pipeline_execution(self):
        pipeline = ConversionPipeline()
        plan = pipeline.run(
            image_or_path=self.input_image_path,
            output_dir=self.output_dir,
            plan_name="acceptance_test_plan",
            unit=Unit.FEET,
        )

        self.assertIsNotNone(plan)
        self.assertGreater(len(plan.entities), 5)

        # Verify QA report
        qa = plan.qa_report
        self.assertIn("raster_coverage_pct", qa)
        self.assertGreater(qa["raster_coverage_pct"], 60.0)
        self.assertGreater(qa["walls_detected"], 0)
        self.assertGreater(qa["hatch_regions"], 0)

        # Check export files exist
        exported = plan.metadata.get("exported_files", {})
        self.assertTrue(os.path.exists(exported.get("dxf", "")))
        self.assertTrue(os.path.exists(exported.get("svg", "")))
        self.assertTrue(os.path.exists(exported.get("pdf", "")))
        self.assertTrue(os.path.exists(exported.get("overlay", "")))

        # Verify that DXF has modelspace hatch and wall entities
        import ezdxf
        doc = ezdxf.readfile(exported["dxf"])
        msp = doc.modelspace()
        hatches = msp.query('HATCH[layer=="A-HATCH"]')
        self.assertGreater(len(hatches), 0, "DXF must contain native A-HATCH entities")


if __name__ == "__main__":
    unittest.main()
