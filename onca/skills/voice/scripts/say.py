#!/usr/bin/env python3
"""Free local narration, one WAV per call: Chatterbox through mlx-audio on an Apple Silicon Mac, Kokoro on
Windows and everything else (Chatterbox there only when --ref gives the founder's own voice).

usage: say.py --text "Words to say." --out DIR [--prefix voice] [--ref FILE] [--exaggeration 0.5] [--voice af_heart] [--speed 1.0]
       say.py --storyboard demo.json --out DIR [--ref FILE] [--exaggeration 0.5]
(run as `python3 say.py ...` on a Mac, `py -3 -X utf8 say.py ...` on Windows)

--storyboard speaks every scene's `say` of a long demo's storyboard into DIR/<scene id>.wav (blank lines
skipped), the files demo.py reads.

--ref is a recording of the founder's own voice that the founder gave for this purpose; without it the
built-in voice speaks. --voice and --speed apply to Kokoro only. Python 3.9+, stdlib only; it runs mlx-audio
(`uv tool install mlx-audio`) on a Mac, and `uv run` with kokoro_say.py or chatterbox_say.py elsewhere (uv fetches
the packages and the model once; nothing else to install).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "video-render" / "scripts"))
import doctor  # noqa: E402

MODEL = "mlx-community/chatterbox-fp16"
GENERATE = "mlx_audio.tts.generate"
KOKORO_CACHE = Path.home() / ".cache" / "onca" / "kokoro"


def engine_for(plat: str, has_ref: bool) -> str:
    """``mlx`` on an Apple Silicon Mac, ``chatterbox`` when a reference voice is given elsewhere, else ``kokoro``."""
    if plat == "mac-arm":
        return "mlx"
    return "chatterbox" if has_ref else "kokoro"


def build_kokoro_command(
    text: str, out_wav: Path, voice: str = "af_heart", speed: float = 1.0, cache_dir: Optional[Path] = None
) -> list:
    """The ``uv run`` command line for kokoro_say.py. ValueError for blank text or a speed outside 0.5 to 2.0."""
    if not text or not text.strip():
        raise ValueError("the text to say is blank")
    if not 0.5 <= speed <= 2.0:
        raise ValueError(f"speed must be from 0.5 to 2.0, not {speed}")
    return ["uv", "run", "--python", "3.12", "--with", "kokoro-onnx==0.6.1", "--with", "soundfile==0.13.1",
            str(HERE / "kokoro_say.py"), "--text", text, "--out", str(out_wav), "--voice", voice,
            "--speed", f"{speed:g}", "--cache", str(cache_dir or KOKORO_CACHE)]


def build_chatterbox_command(text: str, out_wav: Path, ref_audio: Path, exaggeration: float = 0.5) -> list:
    """The ``uv run`` command line for chatterbox_say.py. ValueError for blank text, an exaggeration outside 0 to 1,
    or a reference file that does not exist."""
    if not text or not text.strip():
        raise ValueError("the text to say is blank")
    if not 0 <= exaggeration <= 1:
        raise ValueError(f"exaggeration must be from 0 to 1, not {exaggeration}")
    if not Path(ref_audio).is_file():
        raise ValueError(f"the reference recording {ref_audio} does not exist")
    return ["uv", "run", "--python", "3.11", "--with", "chatterbox-tts==0.1.7", str(HERE / "chatterbox_say.py"),
            "--text", text, "--out", str(out_wav), "--ref", str(ref_audio), "--exaggeration", f"{exaggeration:g}"]


def command_for(plat: str, text: str, out_dir: Path, prefix: str, ref: Optional[Path], exaggeration: float,
                voice: str, speed: float) -> list:
    """The command line that makes ``out_dir/prefix.wav`` on this platform."""
    engine = engine_for(plat, ref is not None)
    if engine == "mlx":
        return build_command(text, out_dir, prefix, ref, exaggeration)
    if engine == "chatterbox":
        return build_chatterbox_command(text, out_dir / f"{prefix}.wav", ref, exaggeration)
    return build_kokoro_command(text, out_dir / f"{prefix}.wav", voice, speed)


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
    if command[0] == "uv":  # winget's uv may not be on this terminal's PATH yet
        command = [doctor.find_tool("uv") or "uv", *command[1:]]
    try:
        code = subprocess.run(command).returncode
    except OSError as err:
        print(f"say.py: cannot run {command[0]}: {err}. Install it as the video-render skill says.", file=sys.stderr)
        return 1
    if code == 0:
        _settle(out_dir, prefix)
    return code


def _settle(out_dir: Path, prefix: str) -> None:
    """mlx-audio may name its file PREFIX_000.wav; the storyboard's contract is PREFIX.wav."""
    want = out_dir / f"{prefix}.wav"
    if not want.exists():
        made = sorted(out_dir.glob(f"{prefix}_*.wav"))
        if made:
            os.replace(made[0], want)


def main(argv: Optional[list] = None, plat: Optional[str] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--text")
    parser.add_argument("--storyboard", type=Path, help="a long demo's demo.json: one WAV per scene that speaks")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--prefix", default="voice")
    parser.add_argument("--ref", type=Path)
    parser.add_argument("--exaggeration", type=float, default=0.5)
    parser.add_argument("--voice", default="af_heart", help="Kokoro voice (Windows and other non-Mac systems)")
    parser.add_argument("--speed", type=float, default=1.0, help="Kokoro speed, 0.5 to 2.0")
    args = parser.parse_args(argv)
    plat = plat or doctor.current_platform()
    if (args.text is None) == (args.storyboard is None):
        print("say.py: give either --text or --storyboard", file=sys.stderr)
        return 2
    if args.storyboard is not None:
        try:
            sb = json.loads(args.storyboard.read_text(encoding="utf-8"))
            problems = _storyboard_problems(sb)
            if problems:
                print("\n".join(f"say.py: {p}" for p in problems), file=sys.stderr)
                return 2
            lines = storyboard_lines(sb)
            commands = [(sid, command_for(plat, words, args.out, sid, args.ref, args.exaggeration, args.voice, args.speed), len(words))
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
        command = command_for(plat, args.text, args.out, args.prefix, args.ref, args.exaggeration, args.voice, args.speed)
    except ValueError as err:
        print(f"say.py: {err}", file=sys.stderr)
        return 2
    args.out.mkdir(parents=True, exist_ok=True)
    return _speak(command, len(args.text), args.out, args.prefix)


if __name__ == "__main__":
    raise SystemExit(main())
