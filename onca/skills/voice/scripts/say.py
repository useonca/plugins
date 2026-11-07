#!/usr/bin/env python3
"""Free local narration with Chatterbox through mlx-audio (Apple Silicon), one WAV per call.

usage: python3 say.py --text "Words to say." --out DIR [--prefix voice] [--ref FILE] [--exaggeration 0.5]
       python3 say.py --storyboard demo.json --out DIR [--ref FILE] [--exaggeration 0.5]

--storyboard speaks every scene's `say` of a long demo's storyboard into DIR/<scene id>.wav (blank lines
skipped), the files demo.py reads.

--ref is a recording of the founder's own voice that the founder gave for this purpose; without it the
built-in voice speaks. Python 3.9+, stdlib only; it runs mlx-audio, which `uv tool install mlx-audio` installs.
"""

from __future__ import annotations

import argparse
import json
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


def storyboard_lines(sb: dict) -> list:
    """(scene id, words) for every scene of a storyboard that says something, in order."""
    return [
        (scene["id"], scene["say"].strip())
        for chapter in sb.get("chapters", [])
        for scene in chapter.get("scenes", [])
        if isinstance(scene.get("say"), str) and scene["say"].strip()
    ]


def _storyboard_problems(sb: dict) -> list:
    """The screen-demo skill's own storyboard check, so no voice is made for a storyboard demo.py would refuse."""
    scripts = Path(__file__).resolve().parents[2] / "screen-demo" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import demo_core

    return demo_core.storyboard_problems(sb)


def _speak(command: list, chars: int, out_dir: Path, prefix: str) -> int:
    """Run one line; the log shows how many characters, never the words. An older take of this prefix is
    removed first, so the new one is the file that is read."""
    shown = list(command)
    shown[shown.index("--text") + 1] = f"<{chars} characters>"
    print("$ " + " ".join(shown), file=sys.stderr)
    for old in [out_dir / f"{prefix}.wav", *out_dir.glob(f"{prefix}_*.wav")]:
        if old.exists():
            old.unlink()
    code = subprocess.run(command).returncode
    if code == 0:
        _settle(out_dir, prefix)
    return code


def _settle(out_dir: Path, prefix: str) -> None:
    """mlx-audio may name its file PREFIX_000.wav; the storyboard's contract is PREFIX.wav."""
    want = out_dir / f"{prefix}.wav"
    if not want.exists():
        made = sorted(out_dir.glob(f"{prefix}_*.wav"))
        if made:
            made[0].rename(want)


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--text")
    parser.add_argument("--storyboard", type=Path, help="a long demo's demo.json: one WAV per scene that speaks")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--prefix", default="voice")
    parser.add_argument("--ref", type=Path)
    parser.add_argument("--exaggeration", type=float, default=0.5)
    args = parser.parse_args(argv)
    if (args.text is None) == (args.storyboard is None):
        print("say.py: give either --text or --storyboard", file=sys.stderr)
        return 2
    if args.storyboard is not None:
        try:
            sb = json.loads(args.storyboard.read_text())
            problems = _storyboard_problems(sb)
            if problems:
                print("\n".join(f"say.py: {p}" for p in problems), file=sys.stderr)
                return 2
            lines = storyboard_lines(sb)
            commands = [(sid, build_command(words, args.out, sid, args.ref, args.exaggeration), len(words))
                        for sid, words in lines]
        except (OSError, ValueError, KeyError, AttributeError) as err:
            print(f"say.py: {err}", file=sys.stderr)
            return 2
        args.out.mkdir(parents=True, exist_ok=True)
        for sid, command, chars in commands:
            code = _speak(command, chars, args.out, sid)
            if code != 0:
                return code
        print(f"say.py: {len(commands)} lines -> {args.out}", file=sys.stderr)
        return 0
    try:
        command = build_command(args.text, args.out, args.prefix, args.ref, args.exaggeration)
    except ValueError as err:
        print(f"say.py: {err}", file=sys.stderr)
        return 2
    args.out.mkdir(parents=True, exist_ok=True)
    return _speak(command, len(args.text), args.out, args.prefix)


if __name__ == "__main__":
    raise SystemExit(main())
