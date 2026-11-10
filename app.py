"""AV Ras2 - Standalone Desktop Application Entry Point.
Artificial Vision, Inc. | https://artificialviz.com
"Find your sense."
"""

import argparse
import base64
import io
import json
import os
import sys
import threading
import time
import webbrowser
import cv2
import numpy as np
from bottle import Bottle, request, response, static_file, run

from engine.pipeline import ConversionPipeline
from engine.scale import Unit, ScaleContext
from engine.document import DocumentLoader
from engine.export_dxf import DXFExportEngine
from engine.export_svg import SVGExportEngine
from engine.export_pdf import PDFExportEngine
from engine.qa import CADQualityAssurance

app = Bottle()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UI_DIR = os.path.join(BASE_DIR, "ui")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Shared in-memory session state
session = {
    "current_image": None,
    "current_filename": "untitled_plan",
    "reconstructed_plan": None,
}


@app.route("/")
def index():
    return static_file("index.html", root=UI_DIR)


@app.route("/<filename:path>")
def static_assets(filename):
    return static_file(filename, root=UI_DIR)


@app.route("/api/demo", method="GET")
def get_demo_plan():
    """Provides a synthetic Matterport floor plan for immediate 1-click testing."""
    demo_path = os.path.join(BASE_DIR, "tests", "test_output_e2e", "synthetic_floor_plan.png")
    if os.path.exists(demo_path):
        img_bgr = cv2.imread(demo_path)
    else:
        # Create on the fly
        img_bgr = np.full((1200, 1200, 3), 255, dtype=np.uint8)
        img_bgr[200:220, 200:1000] = 0
        img_bgr[800:820, 200:1000] = 0
        img_bgr[200:820, 200:220] = 0
        img_bgr[200:820, 980:1000] = 0
        img_bgr[220:450, 580:600] = 0
        img_bgr[510:800, 580:600] = 0
        cv2.ellipse(img_bgr, (600, 450), (60, 60), 0, 0, 90, (0, 0, 0), 2)
        cv2.line(img_bgr, (600, 450), (660, 450), (0, 0, 0), 2)
        img_bgr[1100:1110, 200:400] = 0
        cv2.imwrite(demo_path, img_bgr)

    session["current_image"] = img_bgr
    session["current_filename"] = "matterport_sample_plan.png"

    _, buf = cv2.imencode(".png", img_bgr)
    b64_str = base64.b64encode(buf).decode("utf-8")

    return {
        "available": True,
        "file_name": "matterport_sample_plan.png",
        "image_b64": b64_str,
    }


@app.route("/api/upload", method="POST")
def upload_file():
    upload = request.files.get("file")
    if not upload:
        return {"success": False, "error": "No file uploaded"}

    filename = upload.filename
    temp_path = os.path.join(OUTPUT_DIR, f"temp_{filename}")
    upload.save(temp_path, overwrite=True)

    try:
        intake = DocumentLoader.load_document(temp_path, target_dpi=150)
        page = intake.pages[0]
        session["current_image"] = page.image_np
        session["current_filename"] = filename
        session["text_blocks"] = getattr(page, "text_blocks", [])

        _, buf = cv2.imencode(".png", page.image_np)
        b64_str = base64.b64encode(buf).decode("utf-8")

        return {
            "success": True,
            "filename": filename,
            "width": page.width_px,
            "height": page.height_px,
            "has_native_vectors": page.has_native_vectors,
            "notes": intake.notes,
            "image_b64": b64_str,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.route("/api/convert", method="POST")
def convert_plan():
    if session["current_image"] is None:
        return {"success": False, "error": "No plan image loaded"}

    try:
        data = request.json or {}
        unit_str = data.get("unit", "ft")
        unit_enum = Unit(unit_str)

        calib_pts = data.get("calibration_points")
        real_dist = float(data.get("real_distance", 10.0))

        manual_scale = None
        if calib_pts and len(calib_pts) == 2:
            p1 = (calib_pts[0][0], calib_pts[0][1])
            p2 = (calib_pts[1][0], calib_pts[1][1])
            manual_scale = (p1, p2, real_dist)

        pipeline = ConversionPipeline()
        base_name = os.path.splitext(session["current_filename"])[0]

        plan = pipeline.run(
            image_or_path=session["current_image"],
            manual_scale_pts=manual_scale,
            unit=unit_enum,
            output_dir=OUTPUT_DIR,
            plan_name=base_name,
            external_text_blocks=session.get("text_blocks"),
        )

        session["reconstructed_plan"] = plan

        return {
            "success": True,
            "plan": plan.to_dict(),
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


@app.route("/api/download/dxf", method="GET")
def download_dxf():
    plan = session.get("reconstructed_plan")
    if not plan:
        return "No converted CAD drawing available", 400
    dxf_path = os.path.join(OUTPUT_DIR, f"{plan.plan_name}.dxf")
    if not os.path.exists(dxf_path):
        DXFExportEngine.export(plan, dxf_path)
    return static_file(os.path.basename(dxf_path), root=OUTPUT_DIR, download=True)


@app.route("/api/download/svg", method="GET")
def download_svg():
    plan = session.get("reconstructed_plan")
    if not plan:
        return "No converted CAD drawing available", 400
    svg_path = os.path.join(OUTPUT_DIR, f"{plan.plan_name}.svg")
    if not os.path.exists(svg_path):
        SVGExportEngine.export(plan, svg_path)
    return static_file(os.path.basename(svg_path), root=OUTPUT_DIR, download=True)


@app.route("/api/download/pdf", method="GET")
def download_pdf():
    plan = session.get("reconstructed_plan")
    if not plan:
        return "No converted CAD drawing available", 400
    pdf_path = os.path.join(OUTPUT_DIR, f"{plan.plan_name}.pdf")
    if not os.path.exists(pdf_path):
        PDFExportEngine.export(plan, pdf_path)
    return static_file(os.path.basename(pdf_path), root=OUTPUT_DIR, download=True)


@app.route("/api/download/overlay", method="GET")
def download_overlay():
    plan = session.get("reconstructed_plan")
    if not plan or session["current_image"] is None:
        return "No overlay available", 400
    overlay_path = os.path.join(OUTPUT_DIR, f"{plan.plan_name}_overlay.png")
    if not os.path.exists(overlay_path):
        overlay = CADQualityAssurance.generate_diagnostic_overlay(session["current_image"], plan)
        cv2.imwrite(overlay_path, overlay)
    return static_file(os.path.basename(overlay_path), root=OUTPUT_DIR, download=True)


def start_server(host="127.0.0.1", port=8765):
    run(app, host=host, port=port, quiet=True)


def main():
    parser = argparse.ArgumentParser(description="AV Ras2 Desktop Application (Artificial Vision, Inc.)")
    parser.add_argument("--port", type=int, default=8765, help="Port to run server on")
    parser.add_argument("--browser", action="store_true", help="Launch in default web browser instead of pywebview")
    args = parser.parse_args()

    port = args.port
    server_thread = threading.Thread(target=start_server, args=("127.0.0.1", port), daemon=True)
    server_thread.start()
    time.sleep(0.5)

    app_url = f"http://127.0.0.1:{port}"
    print("=" * 65)
    print("  ARTIFICIAL VISION | AV Ras2 - Raster-to-CAD Reconstruction")
    print("  Tagline: Find your sense.")
    print(f"  Local Desktop Engine: {app_url}")
    print("=" * 65)

    if not args.browser:
        try:
            import webview
            print("[*] Launching AV Ras2 Windows Desktop Application (WebView2)...")
            webview.create_window(
                title="AV Ras2 — Raster to CAD Reconstruction | Artificial Vision, Inc.",
                url=app_url,
                width=1340,
                height=880,
                min_size=(1024, 700),
            )
            webview.start()
            return
        except Exception as e:
            print(f"[*] Native window launcher note ({e}). Opening in default browser...")

    webbrowser.open(app_url)
    print("[*] AV Ras2 running. Press Ctrl+C in terminal to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[*] Shutting down AV Ras2.")


if __name__ == "__main__":
    main()
