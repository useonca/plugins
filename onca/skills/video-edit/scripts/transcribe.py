#!/usr/bin/env python3
"""Word-timed transcript of a video or audio file with parakeet-mlx (local, free).

usage: transcribe.py IN --out words.json [--fix WRONG=RIGHT ...] [--providers providers.json]

Writes [{"i", "text", "start", "end"}]. Fillers (um, uh) are kept on purpose:
they are what the cut removes. The raw parakeet JSON sits next to the output and
is reused while the source is unchanged. Word edges are pulled out of detected
silence (parakeet runs words into the pause after them). --fix corrects names the recognizer
mishears (the product name, a person's name); pass the same fixes everywhere.
--providers: a `transcribe` provider other than the local one (a free local program, or words the
client already has as a file); see references/providers.md.
"""
import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import core, providers, shell  # noqa: E402


def provider_words(spec: dict, wav: Path, work: Path) -> list:
    """Words from a command or file provider, normalised; exit 1 naming the provider when they are not words."""
    out = work / "provider-words.json" if spec["kind"] == "command" else Path(spec["path"])
    if spec["kind"] == "command" and out.exists():
        out.unlink()
    shell.run_provider(spec, {"in": str(wav), "out": str(out), "out_dir": str(work)})
    try:
        return providers.normalize_words(json.loads(out.read_text()))
    except ValueError as exc:
        raise SystemExit(f"provider transcribe ({providers.describe(spec)}): not words: {exc}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--out", required=True)
    ap.add_argument("--fix", action="append", default=[])
    ap.add_argument("--silence-db", default="-35dB", help="raise toward -30dB for a noisy room")
    ap.add_argument("--no-refine", action="store_true", help="keep parakeet's own word edges")
    ap.add_argument("--providers", help="providers.json (default: the local recognizer)")
    a = ap.parse_args()
    spec = providers.resolve("transcribe", shell.load_providers(a.providers))
    shell.log(f"provider transcribe: {providers.describe(spec)}")
    out = Path(a.out)
    work = out.parent / (out.stem + "-asr")
    work.mkdir(parents=True, exist_ok=True)
    src = Path(a.src)
    stamp = f"{src.resolve()}|{src.stat().st_size}|{src.stat().st_mtime_ns}"
    raw_json, stamp_file = work / "audio16k.json", work / "source.txt"
    wav = work / "audio16k.wav"
    if spec["kind"] != "local":
        shell.extract_wav(src, wav)
        words = provider_words(spec, wav, work)
    elif raw_json.exists() and stamp_file.exists() and stamp_file.read_text() == stamp:
        shell.log("transcript cached for this source")
        words = core.words_from_parakeet(json.loads(raw_json.read_text()))
    else:
        shell.extract_wav(src, wav)
        words = core.words_from_parakeet(shell.parakeet_json(wav, work))
        stamp_file.write_text(stamp)
    if not wav.exists():
        shell.extract_wav(src, wav)
    if not a.no_refine:
        sil = core.parse_silences(shell.ffmpeg_log(["-i", str(wav), "-af", f"silencedetect=noise={a.silence_db}:d=0.25"]))
        words = core.refine_with_silences(words, sil)
    words = core.apply_fixes(words, core.parse_fixes(a.fix))
    out.write_text(json.dumps(words, indent=1))
    shell.log(f"{len(words)} words -> {out}")


if __name__ == "__main__":
    main()
