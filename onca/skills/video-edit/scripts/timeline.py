#!/usr/bin/env python3
"""Check, read and render an edit timeline: one ffmpeg pass per output size.

usage: timeline.py check TL.json                      every problem, or `ok` (exit 2 on problems)
       timeline.py words TL.json --out WORDS.json     the kept words on the output timeline
       timeline.py render TL.json --dir OUT_DIR [--encoder auto] [--draft]

render writes OUT_DIR/mix.wav (the sound, once, loudness-normalised in two passes), OUT_DIR/NAME.mp4 per
output (H.264 yuv420p, +faststart, AAC 48 kHz) and OUT_DIR/render.json (timings per step). Captions are
drawn as images by headless Chrome and laid in by ffmpeg. Paths in the timeline are relative to its file.
The schema is in references/timeline.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import compose, core, shell  # noqa: E402
import timeline_core as tlc  # noqa: E402

DRAFT = ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "28", "-pix_fmt", "yuv420p"]


def load(path: str | Path) -> dict:
    """The timeline with every path made absolute (paths in it are relative to its folder)."""
    path = Path(path)
    try:
        tl = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"timeline: cannot read {path}: {exc}", file=sys.stderr)
        raise SystemExit(2)
    base = path.resolve().parent
    if isinstance(tl, dict):
        tl["sources"] = {k: str((base / v).resolve()) for k, v in (tl.get("sources") or {}).items()}
        caps = tl.get("captions") or {}
        if caps.get("words"):
            caps["words"] = {k: str((base / v).resolve()) for k, v in caps["words"].items()}
    return tlc.snap_main(tl) if isinstance(tl, dict) else tl


def probe_sources(tl: dict) -> tuple:
    """(durations, probes, problems): each source's length (None for an image) and size."""
    durations, probes, problems = {}, {}, []
    for key, path in (tl.get("sources") or {}).items() if isinstance(tl, dict) else []:
        if not Path(path).exists():
            problems.append(f"sources.{key}: {path} does not exist")
            continue
        p = shell.probe(path)
        durations[key] = None if tlc.is_image(path) else p["duration"]
        probes[key] = p
    return durations, probes, problems


def check(tl: dict) -> tuple:
    durations, probes, problems = probe_sources(tl)
    if not problems:
        problems = tlc.validate(tl, durations)
    return durations, probes, problems


def fail_on(problems: list) -> None:
    if problems:
        for p in problems:
            print(f"timeline: {p}", file=sys.stderr)
        raise SystemExit(2)


def words_of(tl: dict) -> list:
    caps = tl.get("captions") or {}
    by_src = {k: json.loads(Path(v).read_text(encoding="utf-8")) for k, v in (caps.get("words") or {}).items()}
    return tlc.words_out(tl, by_src)


def render_mix(tl: dict, durations: dict, out_dir: Path, lufs: float) -> Path:
    """The whole sound once: the graph to a float WAV, measured, then one gain and a peak limiter to mix.wav (48 kHz)."""
    g = tlc.audio_graph(tl, durations)
    raw = out_dir / "mix-raw.wav"
    shell.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *[a for i in g["inputs"] for a in i],
               "-filter_complex", g["filter"], "-map", g["out"], "-c:a", "pcm_f32le", "-ar", "48000", str(raw)])
    m = core.parse_ebur128(shell.ffmpeg_log(["-i", str(raw), "-af", "ebur128"]))  # the limiter takes care of the peak
    mix = out_dir / "mix.wav"
    shell.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(raw),
               "-af", core.gain_filter(m, lufs) + ",aresample=48000", "-c:a", "pcm_s16le", str(mix)])
    raw.unlink()
    return mix


def caption_layer(tl: dict, output: dict, words: list, out_dir: Path) -> dict | None:
    """Draw this output's caption states as PNGs and write the concat list; None without captions."""
    caps = tl.get("captions")
    if not caps or not words:
        return None
    band = tlc.output_band(output)
    groups = core.caption_groups(words, max_words=int(caps.get("max_words", 4)))
    states = tlc.caption_states(groups)
    accent = caps.get("accent", "#FFC93C")
    pages = {tlc.state_key(s): compose.caption_card_html(groups[s["group"]], s["lit"], band, accent,
                                                          compose.font_px(groups[s["group"]]["text"], band))
             for s in states}
    folder = out_dir / f"captions-{output['name']}"
    pngs = shell.caption_pngs(pages, (band["width"], band["height"]), folder, compose.FONT_CHECK)
    blank = folder / "blank.png"
    shell.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
               "-i", f"color=c=black@0.0:s={band['width']}x{band['height']},format=rgba", "-frames:v", "1", str(blank)])
    lst = folder / "captions.txt"
    lst.write_text(tlc.caption_concat(states, pngs, str(blank), tlc.main_length(tl)), encoding="utf-8")
    return {"list": str(lst), "x": band["left"], "y": band["top"], "groups": groups}


def render_timeline(tl: dict, out_dir: str | Path, encoder: str, draft: bool, durations: dict, probes: dict) -> dict:
    """Render every output of a timeline `check` passed (its durations and probes); returns the render report."""
    out_dir = Path(out_dir).resolve()  # the caption list names files by absolute path
    out_dir.mkdir(parents=True, exist_ok=True)
    length = tlc.main_length(tl)
    name = tlc.pick_encoder(encoder, shell.encoders_for(encoder))
    enc = DRAFT if draft else tlc.ENCODERS[name]
    shell.log(f"provider encode: local {'draft' if draft else name}")
    report = {"length": length, "encoder": "draft" if draft else name, "steps": {}, "outputs": {}}
    with shell.Clock("sound", length) as c:
        mix = render_mix(tl, durations, out_dir, float(tl.get("loudness", -16)))
    report["steps"]["sound"] = c.seconds
    words = words_of(tl) if tl.get("captions") else []
    for output in tl["outputs"]:
        caps = None
        if words:
            with shell.Clock(f"captions {output['name']}") as c:
                caps = caption_layer(tl, output, words, out_dir)
            report["steps"][f"captions {output['name']}"] = c.seconds
        g = tlc.video_graph(tl, output, probes, caps)
        out = out_dir / f"{output['name']}.mp4"
        args = tlc.render_args(g["inputs"] + [["-i", str(mix)]], g["filter"], [g["out"], f"{len(g['inputs'])}:a"],
                               enc + ["-r", tlc.num(tl.get("fps", 30)), "-t", tlc.num(length)], str(out))
        with shell.Clock(f"render {output['name']}", length) as c:
            shell.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args])
        report["steps"][f"render {output['name']}"] = c.seconds
        report["outputs"][output["name"]] = str(out)
    (out_dir / "render.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check").add_argument("timeline")
    w = sub.add_parser("words")
    w.add_argument("timeline")
    w.add_argument("--out", required=True)
    r = sub.add_parser("render")
    r.add_argument("timeline")
    r.add_argument("--dir", required=True)
    r.add_argument("--encoder", default="auto", help=", ".join(("auto", *tlc.ENCODERS)))
    r.add_argument("--draft", action="store_true", help="a fast low-quality pass to look at")
    a = ap.parse_args()
    tl = load(a.timeline)
    durations, probes, problems = check(tl)
    fail_on(problems)
    if a.cmd == "check":
        print("ok")
    elif a.cmd == "words":
        words = words_of(tl)
        Path(a.out).write_text(json.dumps(words, indent=1), encoding="utf-8")
        shell.log(f"{len(words)} words on the output timeline -> {a.out}")
    else:
        try:
            report = render_timeline(tl, a.dir, a.encoder, a.draft, durations, probes)
        except ValueError as exc:
            print(f"timeline: {exc}", file=sys.stderr)
            raise SystemExit(2)
        shell.log(" | ".join(f"{k} {v} s" for k, v in report["steps"].items()) + f" -> {a.dir}")


if __name__ == "__main__":
    main()
