#!/usr/bin/env python3
"""Cut a source to its approved ranges fast: copy the picture between keyframes, re-encode
only the edges, then check the result and fall back to a full encode when it is not clean.

usage: cut.py EDIT_DIR/edl.json --out OUT.mp4 [--mode auto|smart|encode] [--encoder auto] [--lufs -16]
              [--min-copy 2.0] [--providers providers.json]

The sound is always rendered (25 ms fades at every cut, two-pass loudness) and muxed in. Writes OUT and
OUT.cut.json (pieces, the check, timings, any fallback and why). Same size as the source: use it for the
preview the founder approves and for masters; anything composed or reframed goes through timeline.py.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import core, cut_core, providers, shell, timeline  # noqa: E402
import timeline_core as tlc  # noqa: E402


def smart_video(info: dict, pieces: list, work: Path) -> Path:
    """Each piece to MPEG-TS (copied or re-encoded); returns the concat list that joins them. Edges are always
    re-encoded in software (exact frames, no B-frames) and run several at once: the CPU has the cores."""
    paths = [str(work / f"piece-{k:03d}.ts") for k in range(len(pieces))]

    def one(k: int) -> None:
        p = pieces[k]
        args = cut_core.copy_args(p, info["path"], info["fps"]) if p["mode"] == "copy" else cut_core.encode_args(info, p, "x264")
        shell.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-threads", "2", *args, paths[k]])

    with ThreadPoolExecutor(max(2, min(8, (os.cpu_count() or 4) - 2))) as pool:
        list(pool.map(one, range(len(pieces))))
    lst = work / "pieces.txt"
    lst.write_text(cut_core.concat_list(paths, [round(round((p["end"] - p["start"]) * info["fps"]) / info["fps"], 6) for p in pieces]))
    return lst


def sound_aac(tl: dict, durations: dict, work: Path, lufs: float) -> Path:
    """The cut's sound, mixed and normalised, encoded to AAC (runs while the picture is cut)."""
    mix = timeline.render_mix(tl, durations, work, lufs)
    m4a = work / "sound.m4a"
    shell.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(mix), "-c:a", shell.aac_encoder(), "-b:a", "192k",
               "-ar", "48000", str(m4a)])
    return m4a


def join(pieces_list: Path, sound: Path, out: Path) -> None:
    """The pieces and the sound into the final MP4 in one pass, both copied."""
    shell.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(pieces_list),
               "-i", str(sound), "-map", "0:v", "-map", "1:a", "-c", "copy", "-shortest", "-movflags", "+faststart", str(out)])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("edl")
    ap.add_argument("--out", required=True)
    ap.add_argument("--mode", default="auto", choices=["auto", "smart", "encode"])
    ap.add_argument("--encoder", default="auto", help="auto, videotoolbox, x264 or x264-fast")
    ap.add_argument("--lufs", type=float, default=-16.0)
    ap.add_argument("--min-copy", type=float, default=2.0, help="copy only stretches between keyframes at least this long")
    ap.add_argument("--providers", help="providers.json: an `encode` provider picks the encoder")
    a = ap.parse_args()
    encoder = providers.resolve("encode", shell.load_providers(a.providers)).get("name", a.encoder)
    try:
        name = tlc.pick_encoder(encoder, shell.encoders())
    except ValueError as exc:
        print(f"cut: {exc}", file=sys.stderr)
        raise SystemExit(2)
    report = cut(json.loads(Path(a.edl).read_text()), Path(a.out), a.mode, name, a.lufs, a.min_copy)
    shell.log(f"{report['mode']} cut {report['duration']} s -> {report['out']}")


def cut(edl: dict, out: Path, mode: str, name: str, lufs: float = -16.0, min_copy: float = 2.0,
        decode_check=shell.decode_check) -> dict:
    """Cut `edl` to `out` with encoder `name`; returns the report also written to OUT.cut.json."""
    info = shell.probe(edl["source"])
    out = Path(out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    shell.log(f"provider encode: local {name}")
    report = {"source": edl["source"], "mode": mode, "encoder": name, "steps": {}, "check": [], "fallback": None}
    if mode == "auto":
        mode = "smart" if info.get("codec") in ("h264", "hevc") else "encode"
    if mode == "smart" and info.get("vfr"):
        report["fallback"] = ["variable frame rate: a copy cannot land on exact frames"]
        shell.log("smart cut skipped, encoding instead: the source has a variable frame rate")
        mode = "encode"
    report["mode"] = mode
    tl = tlc.from_edl(edl, [{"name": "cut", "size": f"{info['width']}x{info['height']}"}])
    tl["loudness"] = lufs
    total = tlc.main_length(tl)
    durations = {"main": info["duration"]}
    work = Path(tempfile.mkdtemp(prefix="onca-cut-", dir=out.parent))
    try:
        if mode == "smart":
            with shell.Clock("keyframes") as c:
                kf, pts = shell.packets(info["path"], info.get("start", 0.0))
            report["steps"]["keyframes"] = c.seconds
            if core.uneven_frames(pts, info["fps"]):  # dropped frames: a copy placed by frame counts would drift
                report["fallback"] = ["uneven frame times: a copy cannot land on exact frames"]
                shell.log("smart cut skipped, encoding instead: the frame times leave the frame grid")
                mode = report["mode"] = "encode"
        if mode == "smart":
            pieces = cut_core.plan_pieces(edl["ranges"], kf, info["fps"], min_copy)
            report["pieces"] = pieces
            shell.log(f"{sum(p['mode'] == 'copy' for p in pieces)} copied, {sum(p['mode'] == 'encode' for p in pieces)} re-encoded pieces")
            try:
                with shell.Clock("smart cut", total) as c, ThreadPoolExecutor(1) as pool:
                    sound = pool.submit(sound_aac, tl, durations, work, lufs)  # mixed and encoded while the pieces cut
                    join(smart_video(info, pieces, work), sound.result(), out)
                report["steps"]["smart cut"] = c.seconds
                with shell.Clock("check") as c:
                    frames, errors = decode_check(out, cut_core.join_windows(pieces, info["fps"]))
                    problems = cut_core.check_cut(cut_core.expected_frames(pieces, info["fps"]), frames,
                                                  round(sum(p["end"] - p["start"] for p in pieces), 4), shell.probe(out)["duration"],
                                                  errors, info["fps"])
                report["steps"]["check"] = c.seconds
            except (SystemExit, ValueError) as exc:  # an edge ffmpeg could not match (a 4:2:2 profile, no encoder)
                problems = [f"smart cut failed: {exc}"]
            report["check"] = problems
            if problems:
                shell.log("smart cut failed its check, encoding instead: " + "; ".join(problems))
                report["fallback"] = problems
                mode = "encode"
        if mode == "encode":
            res = timeline.render_timeline(tl, work, name, False, durations, {"main": info})
            shutil.move(res["outputs"]["cut"], out)
            report["steps"].update(res["steps"])
            report["mode"] = "encode"
    finally:
        shutil.rmtree(work, ignore_errors=True)
    report["out"] = str(out)
    report["duration"] = shell.probe(out)["duration"]
    Path(str(out) + ".cut.json").write_text(json.dumps(report, indent=1))
    return report

if __name__ == "__main__":
    main()
