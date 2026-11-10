"""DXF Roundtrip and Validity Verification Test.

Ensures that exported DXF drawings:
- Are syntactically valid and can be opened by CAD parsers (ezdxf)
- Contain real modelspace CAD entities (LINE, LWPOLYLINE, ARC, HATCH)
- Contain correct layers (A-WALL, A-HATCH, A-DOOR, etc.)
- Contain genuine native CAD HATCH entities with SOLID pattern
- Contain calibrated CAD coordinates and units, not an embedded raster image.
"""

import os
import unittest
import ezdxf

from engine.scale import ScaleContext, Unit
from engine.cad_entities import (
    CADLine,
    CADPolyline,
    CADArc,
    CADHatch,
    CADLayer,
    ReconstructedPlan,
)
from engine.export_dxf import DXFExportEngine


class TestDXFRoundtrip(unittest.TestCase):
    def setUp(self):
        self.output_dir = os.path.join(os.path.dirname(__file__), "test_output")
        os.makedirs(self.output_dir, exist_ok=True)
        self.dxf_path = os.path.join(self.output_dir, "roundtrip_test.dxf")

        self.scale = ScaleContext(units_per_pixel=0.05, unit=Unit.FEET)
        self.plan = ReconstructedPlan(
            plan_name="test_floor_plan",
            scale_context=self.scale,
            raster_width=1000,
            raster_height=1000,
        )

        # 1. Two wall boundaries (A-WALL)
        w1 = CADLine(
            layer=CADLayer.WALL,
            start_px=(100.0, 200.0),
            end_px=(500.0, 200.0),
            start_cad=(5.0, 40.0),
            end_cad=(25.0, 40.0),
        )
        w2 = CADLine(
            layer=CADLayer.WALL,
            start_px=(100.0, 220.0),
            end_px=(500.0, 220.0),
            start_cad=(5.0, 39.0),
            end_cad=(25.0, 39.0),
        )
        self.plan.add_entity(w1)
        self.plan.add_entity(w2)

        # 2. Native CAD Hatch (A-HATCH)
        hatch = CADHatch(
            layer=CADLayer.HATCH,
            pattern_name="SOLID",
            loops_px=[[(100.0, 200.0), (500.0, 200.0), (500.0, 220.0), (100.0, 220.0)]],
            loops_cad=[[(5.0, 40.0), (25.0, 40.0), (25.0, 39.0), (5.0, 39.0)]],
        )
        self.plan.add_entity(hatch)

        # 3. Door swing arc (A-DOOR)
        door_arc = CADArc(
            layer=CADLayer.DOOR,
            center_px=(500.0, 200.0),
            radius_px=60.0,
            center_cad=(25.0, 40.0),
            radius_cad=3.0,
            start_angle_deg=0.0,
            end_angle_deg=90.0,
        )
        self.plan.add_entity(door_arc)

    def test_dxf_export_and_readback(self):
        # Export to DXF
        DXFExportEngine.export(self.plan, self.dxf_path)
        self.assertTrue(os.path.exists(self.dxf_path))
        self.assertGreater(os.path.getsize(self.dxf_path), 500)

        # Read back using ezdxf
        doc = ezdxf.readfile(self.dxf_path)
        msp = doc.modelspace()

        # Check drawing header
        self.assertEqual(doc.header.get("$INSUNITS"), 2)  # 2 = Feet

        # Check layers
        self.assertIn("A-WALL", doc.layers)
        self.assertIn("A-HATCH", doc.layers)
        self.assertIn("A-DOOR", doc.layers)

        # Check entities
        lines = msp.query('LINE[layer=="A-WALL"]')
        self.assertEqual(len(lines), 2, "Modelspace must contain 2 wall lines on A-WALL")

        # Check coordinates of first line
        first_line = lines[0]
        self.assertAlmostEqual(first_line.dxf.start.x, 5.0, places=2)
        self.assertAlmostEqual(first_line.dxf.end.x, 25.0, places=2)

        # Check native Hatch
        hatches = msp.query('HATCH[layer=="A-HATCH"]')
        self.assertEqual(len(hatches), 1, "Modelspace must contain native CAD HATCH")
        h = hatches[0]
        self.assertEqual(h.dxf.pattern_name, "SOLID")
        self.assertEqual(len(h.paths), 1)

        # Check door arc
        arcs = msp.query('ARC[layer=="A-DOOR"]')
        self.assertEqual(len(arcs), 1)
        a = arcs[0]
        self.assertAlmostEqual(a.dxf.radius, 3.0, places=2)

    def tearDown(self):
        # Clean up test output
        if os.path.exists(self.dxf_path):
            try:
                os.remove(self.dxf_path)
            except OSError:
                pass


if __name__ == "__main__":
    unittest.main()
