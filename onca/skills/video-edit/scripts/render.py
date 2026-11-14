#!/usr/bin/env python3
"""Render the approved cut at every frame size, in one pass per size (through the timeline).

usage: render.py EDIT_DIR/edl.json --dir EDIT_DIR [--sizes 1080x1920:9x16,1920x1080:16x9]
                 [--lufs -16] [--focus-x 0.5] [--mode auto|crop|fit] [--encoder auto]

Writes EDIT_DIR/cut-<name>.mp4: H.264 yuv420p, +faststart, AAC 48 kHz, loudness normalized in two passes
(the sound is rendered once and shared). Captions are added later by captions.py, or use timeline.py for
captions, cutaways and music in the same pass. Reframe: same aspect scales; a narrower target crops around
--focus-x; a wider target fits the picture over a blurred copy of itself.
"""
import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import core, shell, timeline  # noqa: E402
import timeline_core as tlc  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("edl")
    ap.add_argument("--dir", required=True)
    ap.add_argument("--sizes", default="1080x1920:9x16,1920x1080:16x9")
    ap.add_argument("--lufs", type=float, default=-16.0)
    ap.add_argument("--focus-x", type=float, default=0.5, help="0..1, where the subject sits when cropping to a narrower frame")
    ap.add_argument("--mode", default="auto", choices=["auto", "crop", "fit"])
    ap.add_argument("--encoder", default="auto", help=", ".join(("auto", *tlc.ENCODERS)))
    a = ap.parse_args()
    edl = json.loads(Path(a.edl).read_text(encoding="utf-8"))
    outputs = [{"name": f"cut-{name}", "size": f"{w}x{h}", "focus_x": a.focus_x, "mode": a.mode}
               for w, h, name in core.parse_sizes(a.sizes)]
    tl = tlc.from_edl(edl, outputs)
    tl["loudness"] = a.lufs
    info = shell.probe(edl["source"])
    try:
        report = timeline.render_timeline(tl, a.dir, a.encoder, False, {"main": info["duration"]}, {"main": info})
    except ValueError as exc:
        print(f"render: {exc}", file=sys.stderr)
        raise SystemExit(2)
    (Path(a.dir) / "mix.wav").unlink(missing_ok=True)
    for name, path in report["outputs"].items():
        shell.log(f"{name}: {path}")


if __name__ == "__main__":
    main()
