#!/usr/bin/env python3
"""Measure how fast each editing route runs on this Mac: stream copy, software and hardware
encodes (with picture quality), a 20-cut smart cut against a full re-encode, and voice separation.

usage: speed.py SRC --out speed.md [--seconds 120] [--long LONG.mp4] [--qualities 55,62,70] [--no-separation]

SRC's first --seconds are encoded every way and scored with VMAF against the source (93 or more looks the
same to a viewer). --long (a 10 minute H.264 source) is cut 20 times by cut.py, smart and fully re-encoded.
Writes speed.md (the table and the targets) and speed.json. Renders run one at a time: the Mac has one
media engine, so two at once take twice as long.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import audio, core, cut, providers, shell  # noqa: E402
import timeline_core as tlc  # noqa: E402

VMAF_FLOOR = 93.0


# ---------------------------------------------------------------- pure


def parse_vmaf(log: str) -> float | None:
    m = re.search(r"VMAF score:\s*([\d.]+)", log)
    return round(float(m.group(1)), 2) if m else None


def even_ranges(duration: float, n: int, fps: float, keep: float = 0.8) -> list:
    """n kept ranges spread over the source, each keeping `keep` of its slot (an edl's ranges)."""
    slot = duration / n
    out, t = [], 0.0
    for k in range(n):
        s, e = core.snap(k * slot + slot * (1 - keep) / 2, fps), core.snap((k + 1) * slot - slot * (1 - keep) / 2, fps)
        out.append({"start": s, "end": e, "words": [], "out_start": round(t, 4), "out_end": round(t + e - s, 4)})
        t += e - s
    return out


def pick_quality(rows: list, floor: float = VMAF_FLOOR) -> dict:
    """The lowest VideoToolbox quality whose VMAF reaches the floor; the highest measured when none does."""
    vt = sorted((r for r in rows if r.get("q") is not None and r.get("vmaf") is not None), key=lambda r: r["q"])
    good = [r for r in vt if r["vmaf"] >= floor]
    if good:
        return {"q": good[0]["q"], "vmaf": good[0]["vmaf"], "met": True}
    return {"q": vt[-1]["q"], "vmaf": vt[-1]["vmaf"], "met": False} if vt else {"q": None, "vmaf": None, "met": False}


def targets(rows: dict, picked: dict) -> list:
    """Onca's speed targets against the measured numbers: [{"name", "need", "got", "met"}]."""
    out = []
    smart, full = rows.get("smart cut 20"), rows.get("x264 medium cut 20")
    if smart and full:
        out.append({"name": "20-cut smart cut of the long source", "need": "under 20 s",
                    "got": f"{smart['seconds']:.1f} s", "met": smart["seconds"] < 20})
        ratio = full["seconds"] / smart["seconds"] if smart["seconds"] else 0
        out.append({"name": "smart cut against a full libx264 medium re-encode", "need": "10x faster or more",
                    "got": f"{ratio:.1f}x", "met": ratio >= 10})
    vt, x264 = rows.get(f"videotoolbox q{picked.get('q')}"), rows.get("x264 medium")
    if vt and x264:
        ratio = x264["seconds"] / vt["seconds"] if vt["seconds"] else 0
        out.append({"name": f"VideoToolbox q{picked['q']} against libx264 medium", "need": "2x faster at VMAF 93+",
                    "got": f"{ratio:.1f}x at VMAF {vt.get('vmaf')}", "met": ratio >= 2 and (vt.get("vmaf") or 0) >= VMAF_FLOOR})
    sep = rows.get("separation warm")
    if sep:
        out.append({"name": "voice separation, warm", "need": "20x realtime or more",
                    "got": f"{sep['realtime']:.0f}x", "met": sep["realtime"] >= 20})
    return out


def speed_markdown(machine: str, rows: dict, picked: dict, checks: list) -> str:
    lines = ["# Editing speed on this Mac", "", machine, "",
             "| Route | Time | Realtime | Size | VMAF |", "|---|---|---|---|---|"]
    for name, r in rows.items():
        size = f"{r['mb']:.1f} MB" if r.get("mb") is not None else ""
        vmaf = f"{r['vmaf']:.1f}" if r.get("vmaf") is not None else ""
        lines.append(f"| {name} | {r['seconds']:.1f} s | {r['realtime']:.1f}x | {size} | {vmaf} |")
    lines += ["", f"VideoToolbox quality picked: q{picked['q']} (VMAF {picked['vmaf']}"
              + ("" if picked["met"] else f", under {VMAF_FLOOR:g}: none reached it") + ")", "", "## Targets", ""]
    lines += [f"- {'met' if c['met'] else 'MISSED'}: {c['name']}: {c['got']} (needs {c['need']})" for c in checks]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- shell


def timed_run(cmd: list) -> float:
    with shell.Clock(Path(cmd[-1]).stem) as c:
        shell.run(cmd)
    return c.seconds


def vmaf(dist: Path, ref: str, seconds: float) -> float | None:
    log = shell.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(dist), "-t", str(seconds), "-i", ref,
                     "-lavfi", "[0:v]setpts=PTS-STARTPTS[d];[1:v]setpts=PTS-STARTPTS[r];[d][r]libvmaf=n_threads=8",
                     "-f", "null", "-"]).stderr
    return parse_vmaf(log)


def row(seconds: float, media: float, path: Path | None = None, **extra) -> dict:
    mb = round(path.stat().st_size / 1e6, 2) if path and path.exists() else None
    return {"seconds": seconds, "realtime": round(media / seconds, 1) if seconds else 0.0, "mb": mb, **extra}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("src")
    ap.add_argument("--out", required=True)
    ap.add_argument("--seconds", type=float, default=120.0)
    ap.add_argument("--long", help="a 10 minute H.264 source for the 20-cut test")
    ap.add_argument("--qualities", default="55,62,70")
    ap.add_argument("--no-separation", action="store_true")
    a = ap.parse_args()
    info = shell.probe(a.src)
    secs = min(a.seconds, info["duration"])
    have = shell.encoders()
    rows: dict = {}
    work = Path(tempfile.mkdtemp(prefix="onca-speed-"))
    base = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-t", str(secs), "-i", a.src]
    try:
        out = work / ("copy" + Path(a.src).suffix)  # the same container: a copy keeps the codec
        rows["stream copy"] = row(timed_run(base + ["-c", "copy", str(out)]), secs, out)
        for name, enc in (("x264 medium", tlc.ENCODERS["x264"]), ("x264 veryfast", tlc.ENCODERS["x264-fast"])):
            out = work / f"{name.replace(' ', '-')}.mp4"
            rows[name] = row(timed_run(base + enc + ["-an", str(out)]), secs, out, vmaf=vmaf(out, a.src, secs))
        if "h264_videotoolbox" in have:
            for q in (int(x) for x in a.qualities.split(",")):
                out = work / f"vt-{q}.mp4"
                enc = list(tlc.ENCODERS["videotoolbox"])
                enc[enc.index("-q:v") + 1] = str(q)
                rows[f"videotoolbox q{q}"] = row(timed_run(base + enc + ["-an", str(out)]), secs, out, vmaf=vmaf(out, a.src, secs), q=q)
        picked = pick_quality(list(rows.values()))
        if a.long:
            linfo = shell.probe(a.long)
            edl = {"source": linfo["path"], "fps": linfo["fps"], "width": linfo["width"], "height": linfo["height"],
                   "duration": linfo["duration"], "ranges": even_ranges(linfo["duration"], 20, linfo["fps"]), "words_out": []}
            kept = tlc.main_length(tlc.from_edl(edl, []))
            for label, mode, name in (("smart cut 20", "smart", "videotoolbox" if "h264_videotoolbox" in have else "x264-fast"),
                                      ("x264 medium cut 20", "encode", "x264"),
                                      ("videotoolbox cut 20", "encode", "videotoolbox")):
                if name == "videotoolbox" and "h264_videotoolbox" not in have:
                    continue
                with shell.Clock(label) as c:
                    rep = cut.cut(edl, work / f"{mode}-{name}.mp4", mode, name)
                rows[label] = row(c.seconds, kept, work / f"{mode}-{name}.mp4", mode=rep["mode"])
        if not a.no_separation:
            spec = providers.resolve("separate", None)
            for label in ("separation cold", "separation warm"):
                with shell.Clock(label) as c:
                    audio.separate(a.src, work / label.replace(" ", "-"), spec)
                rows[label] = row(c.seconds, info["duration"])
    finally:
        shutil.rmtree(work, ignore_errors=True)
    machine = shell.run(["sysctl", "-n", "machdep.cpu.brand_string"], check=False).stdout.strip() or "this Mac"
    checks = targets(rows, picked)
    Path(a.out).write_text(speed_markdown(f"{machine}, ffmpeg encoders: {'VideoToolbox' if 'h264_videotoolbox' in have else 'software only'}; "
                                          f"source {Path(a.src).name} {info['width']}x{info['height']} @{info['fps']}, first {secs:g} s",
                                          rows, picked, checks))
    Path(a.out).with_suffix(".json").write_text(json.dumps({"rows": rows, "picked": picked, "targets": checks}, indent=1))
    shell.log(f"speed table -> {a.out}; " + "; ".join(f"{'met' if c['met'] else 'MISSED'} {c['name']}" for c in checks))


if __name__ == "__main__":
    main()
