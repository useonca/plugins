#!/usr/bin/env python3
"""A grayscale depth map of one photo (bright is near) for Onca's parallax, made on the founder's Mac.

usage: uv run --python 3.12 --with torch==2.15.0 --with transformers==5.22.2 --with pillow==13.0.0 \\
         python depth_map.py IMG --out DEPTH.png

broll.py runs that line itself. The model is Depth Anything V2 Small (Apache-2.0, about 100 MB, downloaded
once); only the Small model is licensed for commercial use, so the name is pinned here. This is the one plugin
script that is not standard library: its imports happen inside main(), so the file still parses on Python 3.9.
"""

from __future__ import annotations

import argparse
import sys

MODEL = "depth-anything/Depth-Anything-V2-Small-hf"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Make a depth map of a photo for Onca's parallax.")
    ap.add_argument("img")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    from PIL import Image, ImageFilter, ImageOps
    from transformers import pipeline

    print(f"[b-roll] depth map with {MODEL}", file=sys.stderr)
    pipe = pipeline("depth-estimation", model=MODEL)
    photo = ImageOps.exif_transpose(Image.open(a.img)).convert("RGB")  # upright, as the browser shows it
    depth = pipe(photo)["depth"].convert("L").resize(photo.size, Image.BICUBIC)
    lo, hi = depth.getextrema()
    if hi > lo:
        depth = depth.point(lambda v: round((v - lo) * 255 / (hi - lo)))
    depth.filter(ImageFilter.GaussianBlur(radius=max(1, photo.size[0] // 600))).save(a.out)
    print(f"[b-roll] -> {a.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
