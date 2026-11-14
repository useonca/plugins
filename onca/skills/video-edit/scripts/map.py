#!/usr/bin/env python3
"""The video map: everything Claude reads before planning an edit, in one folder.

usage: map.py SRC --dir EDIT_DIR [--words words.json] [--silence-db -35dB] [--silence-min 0.3]

Writes EDIT_DIR/map.json (probe, phrases, scenes, keyframes, silences, freezes, loudness, repeated takes,
stats), EDIT_DIR/map.md (the transcript by phrase with word indices for plan.json, a marker at every scene
naming its tile on the contact sheets, said-twice runs, stats) and EDIT_DIR/sheets/sheet-NN.png (one frame
from the middle of each scene, 7 per row, 28 per sheet, in scene order: the order is the label).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import core, map_core, shell  # noqa: E402

COLS = 7


def sheets(src: str, scenes: list, out_dir: Path) -> list:
    """One contact sheet per 28 scenes; returns the sheet paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for n in sorted({s["sheet"] for s in scenes}):
        dst = out_dir / f"sheet-{n:02d}.png"
        shell.contact_sheet(src, [s["t"] for s in scenes if s["sheet"] == n], dst, cols=COLS)
        paths.append(str(dst))
    return paths


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("src")
    ap.add_argument("--dir", required=True)
    ap.add_argument("--words", help="words.json from transcribe.py (without it the map has no phrases)")
    ap.add_argument("--silence-db", default="-35dB")
    ap.add_argument("--silence-min", type=float, default=0.3)
    a = ap.parse_args()
    d = Path(a.dir)
    d.mkdir(parents=True, exist_ok=True)
    info = shell.probe(a.src)
    with shell.Clock("map", info["duration"]):
        # one decode for the pauses, the loudness and the frozen picture
        sound = ["-af", f"silencedetect=noise={a.silence_db}:d={a.silence_min},ebur128=peak=true"] if info["has_audio"] else ["-an"]
        log = shell.ffmpeg_log(["-i", a.src, "-vf", "freezedetect=n=-60dB:d=1", *sound])
        silences = core.parse_silences(log, info["duration"]) if info["has_audio"] else []
        loudness = core.parse_ebur128(log) if info["has_audio"] else {}
        freezes = core.parse_freezes(log)
        scenes = shell.scenes(a.src, d)
        keyframes = shell.keyframes(a.src, info["start"])
        words = json.loads(Path(a.words).read_text(encoding="utf-8")) if a.words else []
        m = map_core.build_map(info, words, silences, scenes, keyframes, freezes, loudness)
        m["sheets"] = sheets(a.src, m["scenes"], d / "sheets")
    (d / "map.json").write_text(json.dumps(m, indent=1), encoding="utf-8")
    (d / "map.md").write_text(map_core.map_markdown(m), encoding="utf-8")
    s = m["stats"]
    shell.log(f"{info['duration']} s {m['size']} @{m['fps']} | {s['words']} words | {len(m['scenes'])} scenes on "
              f"{len(m['sheets'])} sheets | keyframe gap max {s['keyframe_gap_max']} s | I {loudness.get('I')} LUFS -> {d / 'map.md'}")


if __name__ == "__main__":
    main()
