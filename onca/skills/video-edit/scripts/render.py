#!/usr/bin/env python3
"""Render the approved cut: one master, then one file per frame size.

usage: render.py EDIT_DIR/edl.json --dir EDIT_DIR [--sizes 1080x1920:9x16,1920x1080:16x9]
                 [--lufs -16] [--focus-x 0.5] [--mode auto|crop|fit]

Writes EDIT_DIR/cut-<name>.mp4: H.264 yuv420p, +faststart, AAC 48 kHz, loudness
normalized in two passes. Captions are added later by captions.py.
Reframe: same aspect scales; a narrower target crops around --focus-x;
a wider target fits the picture over a blurred copy of itself.
"""
import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import core, shell  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("edl")
    ap.add_argument("--dir", required=True)
    ap.add_argument("--sizes", default="1080x1920:9x16,1920x1080:16x9")
    ap.add_argument("--lufs", type=float, default=-16.0)
    ap.add_argument("--focus-x", type=float, default=0.5, help="0..1, where the subject sits when cropping to a narrower frame")
    ap.add_argument("--mode", default="auto", choices=["auto", "crop", "fit"])
    ap.add_argument("--crf", type=int, default=18)
    a = ap.parse_args()
    edl = json.loads(Path(a.edl).read_text())
    d = Path(a.dir)
    master = d / "cut-master.mov"
    shell.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", edl["source"],
               "-filter_complex", core.cut_graph(edl["ranges"]), "-map", "[v]", "-map", "[a]",
               "-c:v", "libx264", "-crf", "12", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "pcm_s16le", str(master)])
    m = core.parse_loudnorm(shell.ffmpeg_log(["-i", str(master), "-vn", "-af", f"loudnorm=I={a.lufs}:TP=-1.5:LRA=11:print_format=json"]))
    shell.log(f"master {shell.probe(master)['duration']} s (edl {edl['total']} s), measured {m['input_i']} LUFS")
    for w, h, name in core.parse_sizes(a.sizes):
        out = d / f"cut-{name}.mp4"
        vf = core.reframe_filter(edl["width"], edl["height"], w, h, a.focus_x, a.mode)
        shell.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(master),
                   "-filter_complex", f"[0:v]{vf}[v]", "-map", "[v]", "-map", "0:a",
                   "-af", core.loudnorm_apply(m, a.lufs) + ",aresample=48000",
                   "-c:v", "libx264", "-crf", str(a.crf), "-preset", "medium", "-profile:v", "high", "-pix_fmt", "yuv420p",
                   "-r", str(edl["fps"]), "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)])
        shell.log(f"{name}: {out}")


if __name__ == "__main__":
    main()
