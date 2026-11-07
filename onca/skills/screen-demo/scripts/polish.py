#!/usr/bin/env python3
"""Polish any REC folder (a recording, a rebuilt flow, a native capture) into a finished clip: the footage on
a styled stage, an auto zoom to each click, a smoothed, enlarged cursor (or a finger dot) and a ripple on
each press. Free and local, through Onca's render engine.

usage: polish.py REC --out OUT.mp4 [--size 1920x1080] [--zoom 1.8] [--no-zoom] [--pointer arrow|finger]
                 [--background A,B] [--project DIR] [--draft]

REC holds raw.mp4 and clicks.json (record.py and flow.py write both). A 9:16 size (1080x1920) keeps a base
zoom of 1.4 so the screen fills the frame. Writes the project (OUT-hf/), its check.json, OUT.mp4 (silent)
and OUT-contact.png.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import polish_core  # noqa: E402
import polish_html  # noqa: E402
import shared  # noqa: E402

PORTRAIT_BASE = 1.4


def load_rec(rec: Path) -> dict:
    problems = []
    if not rec.is_dir():
        shared.bad_input([f"no REC folder at {rec}"])
    if not (rec / "raw.mp4").exists():
        problems.append(f"{rec}/raw.mp4 is missing (record.py or flow.py writes it)")
    log = None
    if not (rec / "clicks.json").exists():
        problems.append(f"{rec}/clicks.json is missing (record.py or flow.py writes it)")
    else:
        try:
            log = json.loads((rec / "clicks.json").read_text())
            if not {"viewport", "duration", "events"} <= set(log):
                problems.append(f"{rec}/clicks.json needs viewport, duration and events")
        except ValueError as e:
            problems.append(f"{rec}/clicks.json is not JSON: {e}")
    if problems:
        shared.bad_input(problems)
    return log


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Polish a REC folder into a finished, silent clip.")
    ap.add_argument("rec")
    ap.add_argument("--out", required=True)
    ap.add_argument("--size", default="1920x1080")
    ap.add_argument("--zoom", type=float, default=1.8)
    ap.add_argument("--no-zoom", action="store_true")
    ap.add_argument("--pointer", choices=polish_html.POINTERS, help="default: what clicks.json says, else arrow")
    ap.add_argument("--background", help="two gradient colours, e.g. '#151412,#3A3326' (the brand's when known)")
    ap.add_argument("--project")
    ap.add_argument("--draft", action="store_true")
    a = ap.parse_args(argv)
    rec = Path(a.rec)
    log = load_rec(rec)
    out_w, out_h = shared.parse_size(a.size)
    background = ("#151412", "#3A3326")
    if a.background:
        parts = [p.strip() for p in a.background.split(",")]
        if len(parts) != 2 or not all(parts):
            shared.bad_input(["--background needs two colours, A,B"])
        background = (parts[0], parts[1])
    vw, vh = log["viewport"]["w"], log["viewport"]["h"]
    duration = round(min(log["duration"], shared.probe(rec / "raw.mp4")["duration"]), 3)
    base = PORTRAIT_BASE if out_h > out_w else 1.0
    plan = [] if a.no_zoom else polish_core.zoom_plan(log, scale=max(a.zoom, base))
    layout = polish_core.stage_layout(out_w, out_h, vw, vh)
    view = (out_w / layout["scale"], out_h / layout["scale"])
    camera = polish_core.camera_keys(plan, vw, vh, duration, base=base, view=view)
    cursor = polish_core.cursor_keys(log)
    clicks = [e for e in log["events"] if e["kind"] in ("click", "tap")]
    pointer = a.pointer or log.get("pointer", "arrow")
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    proj = Path(a.project or out.with_suffix("").as_posix() + "-hf")
    (proj / "assets").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(rec / "raw.mp4", proj / "assets" / "raw.mp4")
    (proj / "index.html").write_text(polish_html.index_html(layout, camera, cursor, clicks, out_w, out_h, duration,
                                                            background=background, pointer=pointer))
    (proj / "plan.json").write_text(json.dumps({"zoom": plan, "camera": camera, "cursor": cursor}, indent=1))
    shared.log(f"{len(plan)} zoom segments, {len(cursor)} cursor keys, {len(clicks)} presses, {pointer}, {out_w}x{out_h}")
    raw = proj / "render.mp4"
    shared.render(proj, raw, a.draft)
    shared.finish(raw, out, sound=False)
    sheet = shared.contact(out, duration)
    shared.log(f"-> {out} (contact sheet {sheet})")


if __name__ == "__main__":
    main()
