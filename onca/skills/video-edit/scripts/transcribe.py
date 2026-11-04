#!/usr/bin/env python3
"""Word-timed transcript of a video or audio file with parakeet-mlx (local, free).

usage: transcribe.py IN --out words.json [--fix WRONG=RIGHT ...]

Writes [{"i", "text", "start", "end"}]. Fillers (um, uh) are kept on purpose:
they are what the cut removes. The raw parakeet JSON sits next to the output and
is reused while the source is unchanged. Word edges are pulled out of detected
silence (parakeet runs words into the pause after them). --fix corrects names the recognizer
mishears (the product name, a person's name); pass the same fixes everywhere.
"""
import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import core, shell  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--out", required=True)
    ap.add_argument("--fix", action="append", default=[])
    ap.add_argument("--silence-db", default="-35dB", help="raise toward -30dB for a noisy room")
    ap.add_argument("--no-refine", action="store_true", help="keep parakeet's own word edges")
    a = ap.parse_args()
    out = Path(a.out)
    work = out.parent / (out.stem + "-asr")
    work.mkdir(parents=True, exist_ok=True)
    src = Path(a.src)
    stamp = f"{src.resolve()}|{src.stat().st_size}|{src.stat().st_mtime_ns}"
    raw_json, stamp_file = work / "audio16k.json", work / "source.txt"
    if raw_json.exists() and stamp_file.exists() and stamp_file.read_text() == stamp:
        shell.log("transcript cached for this source")
        raw = json.loads(raw_json.read_text())
    else:
        shell.extract_wav(src, work / "audio16k.wav")
        raw = shell.parakeet_json(work / "audio16k.wav", work)
        stamp_file.write_text(stamp)
    wav = work / "audio16k.wav"
    if not wav.exists():
        shell.extract_wav(src, wav)
    sil = core.parse_silences(shell.ffmpeg_log(["-i", str(wav), "-af", f"silencedetect=noise={a.silence_db}:d=0.25"]))
    words = core.words_from_parakeet(raw)
    if not a.no_refine:
        words = core.refine_with_silences(words, sil)
    words = core.apply_fixes(words, core.parse_fixes(a.fix))
    out.write_text(json.dumps(words, indent=1))
    shell.log(f"{len(words)} words -> {out}")


if __name__ == "__main__":
    main()
