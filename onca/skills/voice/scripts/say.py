#!/usr/bin/env python3
"""Free local narration with Chatterbox through mlx-audio (Apple Silicon), one WAV per call.

usage: python3 say.py --text "Words to say." --out DIR [--prefix voice] [--ref FILE] [--exaggeration 0.5]

--ref is a recording of the founder's own voice that the founder gave for this purpose; without it the
built-in voice speaks. Python 3.9+, stdlib only; it runs mlx-audio, which `uv tool install mlx-audio` installs.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Optional

MODEL = "mlx-community/chatterbox-fp16"
GENERATE = "mlx_audio.tts.generate"


def build_command(
    text: str, out_dir: Path, prefix: str, ref_audio: Optional[Path] = None, exaggeration: float = 0.5
) -> list:
    """The mlx-audio command line. ValueError for blank text, an exaggeration outside 0 to 1, or a reference
    file that does not exist."""
    if not text or not text.strip():
        raise ValueError("the text to say is blank")
    if not 0 <= exaggeration <= 1:
        raise ValueError(f"exaggeration must be from 0 to 1, not {exaggeration}")
    command = [
        GENERATE, "--model", MODEL, "--exaggeration", str(exaggeration),
        "--output_path", str(out_dir), "--file_prefix", prefix,
        "--join_audio", "--audio_format", "wav", "--text", text,
    ]
    if ref_audio is not None:
        if not Path(ref_audio).is_file():
            raise ValueError(f"the reference recording {ref_audio} does not exist")
        command += ["--ref_audio", str(ref_audio)]
    return command


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--text", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--prefix", default="voice")
    parser.add_argument("--ref", type=Path)
    parser.add_argument("--exaggeration", type=float, default=0.5)
    args = parser.parse_args(argv)
    try:
        command = build_command(args.text, args.out, args.prefix, args.ref, args.exaggeration)
    except ValueError as err:
        print(f"say.py: {err}", file=sys.stderr)
        return 2
    args.out.mkdir(parents=True, exist_ok=True)
    print("$ " + " ".join(command[:-1]) + " --text <" + str(len(args.text)) + " characters>", file=sys.stderr)
    return subprocess.run(command).returncode


if __name__ == "__main__":
    raise SystemExit(main())
