#!/usr/bin/env python3
"""One WAV of speech in the founder's own voice with Chatterbox (chatterbox-tts), free and local.

usage: uv run --python 3.11 --with chatterbox-tts==0.1.7 chatterbox_say.py
           --text "Words." --out voice.wav --ref MY_VOICE.wav [--exaggeration 0.5]

Opt-in route for a founder who gave a recording of their own voice (--ref) and has an NVIDIA GPU: on a CPU it is
slow. The model (a few GB) downloads once into the Hugging Face cache under ~/.cache/onca/chatterbox. Resemble AI
publishes Chatterbox under the MIT licence; its tests ran on Linux, so Windows is not verified.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Optional


def main(argv: Optional[list] = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--text", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--ref", required=True, type=Path)
    parser.add_argument("--exaggeration", type=float, default=0.5)
    args = parser.parse_args(argv)
    os.environ.setdefault("HF_HOME", str(Path.home() / ".cache" / "onca" / "chatterbox"))
    import torch  # noqa: E402  (heavy imports only here: the script is also read by tests)
    import torchaudio  # noqa: E402
    from chatterbox.tts import ChatterboxTTS  # noqa: E402

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"chatterbox_say: {len(args.text)} characters on {device}", file=sys.stderr)
    model = ChatterboxTTS.from_pretrained(device=device)
    wav = model.generate(args.text, audio_prompt_path=str(args.ref), exaggeration=args.exaggeration)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    torchaudio.save(str(args.out), wav, model.sr)
    print(f"chatterbox_say: -> {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
