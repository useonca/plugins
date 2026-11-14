#!/usr/bin/env python3
"""Voice and sound for an edit: split the voice from the room, clean it, measure loudness.

usage: audio.py separate SRC --out-dir STEMS [--providers providers.json]
       audio.py clean IN --out OUT.wav [--denoise light|off] [--lufs -16]
       audio.py measure IN                       prints {"I", "LRA", "TP"} as JSON

separate writes STEMS/vocals.wav (the voice alone) and STEMS/background.wav (everything else). The local
separator is the free one `python3 ../../video-render/scripts/doctor.py check` lists as optional; a `separate`
provider may be another free program (writes both files into {out_dir}) or a folder that already holds them.
clean: rumble filter, light denoise, gentle compression, then two-pass loudness to --lufs at 48 kHz.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import core, providers, shell  # noqa: E402
import timeline_core as tlc  # noqa: E402

STEMS = ("vocals.wav", "background.wav")


def demucs_command(tool_path: str, wav: Path, work: Path, plat: str) -> list:
    """The separator's command line: demucs-mlx on an Apple Silicon Mac (compiled: about 15% faster), else demucs."""
    return [tool_path, "-n", "htdemucs", *(["--compile"] if plat == "mac-arm" else []), "-o", str(work), str(wav)]


def separate_local(wav: Path, out_dir: Path, work: Path, plat: str | None = None) -> None:
    """The local separator writes four stems; the background is drums + bass + other, mixed without scaling."""
    plat = plat or shell.doctor.current_platform()
    shell.run(demucs_command(shell.tool("demucs-mlx" if plat == "mac-arm" else "demucs"), wav, work, plat))
    found = {p.name: p for p in work.rglob("*.wav")}
    missing = [n for n in ("vocals.wav", "drums.wav", "bass.wav", "other.wav") if n not in found]
    if missing:
        raise SystemExit(f"provider separate (local): no {', '.join(missing)} under {work}")
    shutil.move(str(found["vocals.wav"]), out_dir / "vocals.wav")
    shell.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(found["drums.wav"]), "-i", str(found["bass.wav"]),
               "-i", str(found["other.wav"]), "-filter_complex", "amix=inputs=3:normalize=0", str(out_dir / "background.wav")])


def separate(src: str, out_dir: Path, spec: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    in_place = spec["kind"] == "file" and Path(spec["path"]).resolve() == out_dir.resolve()
    for stem in [] if in_place else STEMS:  # an earlier run's stem never stands in for a missing one
        (out_dir / stem).unlink(missing_ok=True)
    name = f"provider separate ({providers.describe(spec)})"
    work = Path(tempfile.mkdtemp(prefix="onca-separate-", dir=out_dir))
    try:
        wav = work / "source.wav"
        shell.extract_wav(src, wav, rate=44100, channels=2)
        if spec["kind"] == "local":
            separate_local(wav, out_dir, work)
        elif spec["kind"] == "command":
            shell.run_provider(spec, {"in": str(wav), "out_dir": str(out_dir)})
        else:
            shell.run_provider(spec, {})
            folder = Path(spec["path"])
            for stem in STEMS:
                if (folder / stem).exists() and (folder / stem).resolve() != (out_dir / stem).resolve():
                    shutil.copyfile(folder / stem, out_dir / stem)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    missing = [s for s in STEMS if not (out_dir / s).exists()]
    if missing:
        for stem in [] if in_place else STEMS:  # no half output: both stems or none (never the founder's own files)
            (out_dir / stem).unlink(missing_ok=True)
        raise SystemExit(f"{name}: no {', '.join(missing)} in {out_dir}")


def clean(src: str, out: Path, denoise: str, lufs: float) -> dict:
    chain = tlc.clean_chain(denoise)
    m = core.parse_ebur128(shell.ffmpeg_log(["-i", src, "-vn", "-af", f"{chain},ebur128=peak=true"]))
    # the denoiser puts the voice a window late; trimmed off, so the clean voice keeps the picture's clock
    delay = shell.filter_delay(chain, shell.probe(src)["audio_rate"] or 48000)
    shift = f",apad=pad_dur={delay},atrim=start={delay},asetpts=PTS-STARTPTS" if delay else ""
    shell.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", src, "-vn",
               "-af", f"{chain}{shift},{core.gain_filter(m, lufs)},aresample=48000", "-c:a", "pcm_s16le", str(out)])
    return m


def measure(src: str) -> dict:
    return core.parse_ebur128(shell.ffmpeg_log(["-i", src, "-vn", "-af", "ebur128=peak=true"]))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("separate")
    s.add_argument("src")
    s.add_argument("--out-dir", required=True)
    s.add_argument("--providers")
    c = sub.add_parser("clean")
    c.add_argument("src")
    c.add_argument("--out", required=True)
    c.add_argument("--denoise", default="light", choices=["light", "off"])
    c.add_argument("--lufs", type=float, default=-16.0)
    sub.add_parser("measure").add_argument("src")
    a = ap.parse_args()
    if a.cmd == "separate":
        spec = providers.resolve("separate", shell.load_providers(a.providers))
        shell.log(f"provider separate: {providers.describe(spec)}")
        length = shell.probe(a.src)["duration"]
        with shell.Clock("separate", length):
            separate(a.src, Path(a.out_dir), spec)
        shell.log(f"voice and background -> {a.out_dir}")
    elif a.cmd == "clean":
        with shell.Clock("clean", shell.probe(a.src)["duration"]):
            m = clean(a.src, Path(a.out), a.denoise, a.lufs)
        shell.log(f"cleaned ({a.denoise} denoise), {m['I']} -> {a.lufs} LUFS -> {a.out}")
    else:
        print(json.dumps(measure(a.src)))


if __name__ == "__main__":
    main()
