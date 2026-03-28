#!/usr/bin/env python3
"""
Processes the 3 installation screenshots for the /extension command.
Blurs the file listing area in step2 to redact internal folder names.

Usage:
    python scripts/process-screenshots.py \
        --step1 /path/to/screenshot1.png \
        --step2 /path/to/screenshot2.png \
        --step3 /path/to/screenshot3.png \
        --out passport-telegram/src/passport_telegram/assets/extension/
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageFilter


def blur_region(img: Image.Image, box: tuple[int, int, int, int], radius: int = 20) -> Image.Image:
    """Blur a rectangular region of the image in-place."""
    region = img.crop(box)
    blurred = region.filter(ImageFilter.GaussianBlur(radius=radius))
    img.paste(blurred, box)
    return img


def process(src: Path, dst: Path, blur_boxes: list[tuple[int, int, int, int]]) -> None:
    with Image.open(src) as img:
        # Pillow opens Retina screenshots at full 2x pixel dimensions.
        # If the image is exactly 2x the expected display size, scale boxes.
        w, h = img.size
        dpi = img.info.get("dpi", (72, 72))
        scale = 2 if dpi[0] >= 144 else 1
        for box in blur_boxes:
            scaled = tuple(v * scale for v in box)
            blur_region(img, scaled)
        dst.parent.mkdir(parents=True, exist_ok=True)
        img.save(dst, format="PNG", optimize=True)
        print(f"Saved {dst} ({w}x{h}px, scale={scale}x)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--step1", required=True)
    parser.add_argument("--step2", required=True)
    parser.add_argument("--step3", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    out = Path(args.out)

    # step1: chrome://extensions page with Dev Mode toggle — no sensitive data
    process(Path(args.step1), out / "step1.png", blur_boxes=[])

    # step2: file-picker dialog — blur the entire file listing content area
    # NOTE: These coordinates were calibrated for the specific screenshots taken
    # on 2026-03-28. If re-running with different screenshots, re-calibrate by
    # opening the source image at 1x and measuring the region to redact.
    # Coordinates are at 1x display pixels; the script scales for Retina 2x.
    # Adjust if the output looks off: (left, top, right, bottom)
    # Covers: breadcrumb path ("passport-reader") + all folder name rows
    process(
        Path(args.step2),
        out / "step2.png",
        blur_boxes=[
            (400, 255, 815, 275),   # breadcrumb path bar ("passport-reader")
            (400, 285, 1065, 565),  # file listing rows (folder names + metadata)
        ],
    )

    # step3: extension installed — no sensitive data
    process(Path(args.step3), out / "step3.png", blur_boxes=[])


if __name__ == "__main__":
    main()
