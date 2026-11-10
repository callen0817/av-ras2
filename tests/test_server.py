"""Integration test for Desktop Application Server and REST endpoints."""

import json
import threading
import time
import unittest
import urllib.request
from app import start_server


class TestAppServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = 8991
        cls.server_thread = threading.Thread(target=start_server, args=("127.0.0.1", cls.port), daemon=True)
        cls.server_thread.start()
        time.sleep(1.0)
        cls.base_url = f"http://127.0.0.1:{cls.port}"

    def test_01_index_html(self):
        url = f"{self.base_url}/"
        with urllib.request.urlopen(url) as res:
            self.assertEqual(res.status, 200)
            html = res.read().decode("utf-8")
            self.assertIn("ARTIFICIAL VISION", html)
            self.assertIn("AV Ras2", html)

    def test_02_demo_endpoint(self):
        url = f"{self.base_url}/api/demo"
        with urllib.request.urlopen(url) as res:
            self.assertEqual(res.status, 200)
            data = json.loads(res.read().decode("utf-8"))
            self.assertTrue(data.get("available"))
            self.assertIn("image_b64", data)

    def test_03_convert_endpoint(self):
        url = f"{self.base_url}/api/convert"
        req = urllib.request.Request(
            url,
            data=json.dumps({"unit": "ft"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req) as res:
            self.assertEqual(res.status, 200)
            data = json.loads(res.read().decode("utf-8"))
            self.assertTrue(data.get("success"))
            plan = data["plan"]
            self.assertGreater(len(plan["entities"]), 0)
            self.assertGreater(plan["qa_report"]["raster_coverage_pct"], 50.0)

    def test_04_download_dxf(self):
        url = f"{self.base_url}/api/download/dxf"
        with urllib.request.urlopen(url) as res:
            self.assertEqual(res.status, 200)
            content = res.read()
            self.assertGreater(len(content), 1000)
            self.assertIn(b"ENTITIES", content)
            self.assertIn(b"A-WALL", content)
            self.assertIn(b"A-HATCH", content)


if __name__ == "__main__":
    unittest.main()
