"""AV Ras2 Command-Line Interface (CLI).

Enables batch and headless conversion of raster architectural plans into scaled CAD drawings.
Artificial Vision, Inc.
"""

import argparse
import os
import sys
from engine.pipeline import ConversionPipeline
from engine.scale import Unit


def main():
    parser = argparse.ArgumentParser(
        description="AV Ras2: Matterport & Raster Floor Plan to Vector CAD Converter (Artificial Vision, Inc.)"
    )
    parser.add_argument("input", help="Path to input raster file or directory of plans (PDF, PNG, JPG, TIFF)")
    parser.add_argument("-o", "--output", default="output", help="Directory to save exported CAD drawings")
    parser.add_argument("-u", "--unit", default="ft", choices=["ft", "in", "m", "mm", "cm"], help="CAD drawing units")
    parser.add_argument("-p", "--page", type=int, default=1, help="Page number to convert (for multi-page PDFs)")
    parser.add_argument("--dpi", type=int, default=150, help="Target rendering DPI for PDF raster pages")
    parser.add_argument("--scale", type=float, help="Manual units-per-pixel scale override")

    args = parser.parse_args()

    input_path = os.path.abspath(args.input)
    output_dir = os.path.abspath(args.output)
    os.makedirs(output_dir, exist_ok=True)

    unit_enum = Unit(args.unit)
    pipeline = ConversionPipeline()

    if os.path.isdir(input_path):
        # Batch mode
        supported_exts = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".pdf", ".bmp")
        files = [
            os.path.join(input_path, f)
            for f in os.listdir(input_path)
            if os.path.splitext(f)[1].lower() in supported_exts
        ]
        print(f"[*] AV Ras2 Batch Processing: Found {len(files)} drawing(s) in {input_path}")
        success_count = 0
        for f in files:
            print(f" -> Converting {os.path.basename(f)}...")
            try:
                plan = pipeline.run(
                    image_or_path=f,
                    page_num=args.page,
                    unit=unit_enum,
                    target_dpi=args.dpi,
                    output_dir=output_dir,
                )
                print(f"    [OK] Generated DXF: {plan.metadata['exported_files']['dxf']}")
                success_count += 1
            except Exception as e:
                print(f"    [ERROR] Failed to convert {os.path.basename(f)}: {e}")
        print(f"[*] Batch conversion complete. {success_count}/{len(files)} files successfully converted.")

    elif os.path.isfile(input_path):
        print(f"[*] AV Ras2 Converting: {os.path.basename(input_path)}")
        try:
            plan = pipeline.run(
                image_or_path=input_path,
                page_num=args.page,
                unit=unit_enum,
                target_dpi=args.dpi,
                output_dir=output_dir,
            )
            print("[+] Conversion Successful!")
            print(f"    - DXF Drawing: {plan.metadata['exported_files']['dxf']}")
            print(f"    - SVG Vector:  {plan.metadata['exported_files']['svg']}")
            print(f"    - Vector PDF:  {plan.metadata['exported_files']['pdf']}")
            print(f"    - QA Overlay:  {plan.metadata['exported_files']['overlay']}")
            print(f"    - Raster Coverage: {plan.qa_report.get('raster_coverage_pct', 0)}%")
            print(f"    - Reconstructed Walls: {plan.qa_report.get('walls_detected', 0)}")
            print(f"    - Reconstructed Hatches: {plan.qa_report.get('hatch_regions', 0)}")
        except Exception as e:
            print(f"[-] Conversion error: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print(f"[-] Input path not found: {input_path}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
