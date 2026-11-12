#!/usr/bin/env python3
"""One WAV of speech with Kokoro (kokoro-onnx), free and local, on CPU: the default voice off the Mac.

usage: uv run --python 3.12 --with kokoro-onnx==0.6.1 --with soundfile kokoro_say.py
           --text "Words." --out voice.wav [--voice af_heart] [--speed 1.0] [--cache DIR]

say.py runs this through uv, so the founder installs nothing by hand. The model (about 330 MB) and the voice
file download once into the cache folder (default ~/.cache/onca/kokoro) and are reused. Kokoro is Apache-2.0.
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.request
from pathlib import Path
from typing import Optional

BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
FILES = ("kokoro-v1.0.onnx", "voices-v1.0.bin")


def fetch(cache: Path) -> tuple:
    """The model and voices files in ``cache``, downloaded on the first run (to a temp name, then moved)."""
    cache.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        target = cache / name
        if target.is_file() and target.stat().st_size > 0:
            continue
        print(f"kokoro_say: downloading {name} once into {cache}", file=sys.stderr)
        part = cache / (name + ".part")
        urllib.request.urlretrieve(BASE + name, part)
        os.replace(part, target)
    return cache / FILES[0], cache / FILES[1]


def main(argv: Optional[list] = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--text", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--voice", default="af_heart")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--cache", type=Path, default=Path.home() / ".cache" / "onca" / "kokoro")
    args = parser.parse_args(argv)
    model, voices = fetch(args.cache)
    import soundfile  # noqa: E402  (heavy imports only here: the script is also read by tests)
    from kokoro_onnx import Kokoro  # noqa: E402

    samples, rate = Kokoro(str(model), str(voices)).create(args.text, voice=args.voice, speed=args.speed, lang="en-us")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    soundfile.write(str(args.out), samples, rate)
    print(f"kokoro_say: {len(args.text)} characters -> {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
