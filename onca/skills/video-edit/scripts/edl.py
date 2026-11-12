#!/usr/bin/env python3
"""Turn Claude's keep plan into the cut list: edl.json for the renderer, edl.md for the founder.

usage: edl.py SRC --words words.json --plan plan.json --dir EDIT_DIR
              [--pad-before 0.06] [--pad-after 0.09] [--max-pause 0.4] [--tight-pause 0.15]

plan.json (Claude writes it from takes.md):
  {"keep": [{"from": 0, "to": 5, "reason": "hook"}, ...],      word indices, inclusive, in play order
   "drop": [{"from": 6, "to": 16, "reason": "um + false start"}, ...],  labels for the cut lines
   "retext": {"79": "days.", "82": "so"}}        optional caption wording per word index

Pauses inside a kept span over --max-pause become --tight-pause. Every edge snaps
to a frame and stays between words, so no word is clipped.
"""
import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import core, shell  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--words", required=True)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--dir", required=True)
    ap.add_argument("--pad-before", type=float, default=0.06)
    ap.add_argument("--pad-after", type=float, default=0.09)
    ap.add_argument("--max-pause", type=float, default=0.4)
    ap.add_argument("--tight-pause", type=float, default=0.15)
    ap.add_argument("--no-settle", action="store_true", help="keep the edges from the word times alone")
    a = ap.parse_args()
    info = shell.probe(a.src)
    words = json.loads(Path(a.words).read_text(encoding="utf-8"))
    plan = json.loads(Path(a.plan).read_text(encoding="utf-8"))
    settings = {k: getattr(a, k) for k in ("pad_before", "pad_after", "max_pause", "tight_pause")}
    ranges = core.build_ranges(words, plan["keep"], fps=info["fps"], duration=info["duration"], **settings)
    if info["has_audio"] and not a.no_settle:  # the word times can be a syllable off: cut in the quiet beside them
        lv = shell.levels(a.src)
        settled = core.settle_edges(ranges, words, lv, core.quiet_floor(lv), fps=info["fps"])
        moved = sum((x["start"], x["end"]) != (y["start"], y["end"]) for x, y in zip(ranges, settled)) if len(settled) == len(ranges) else len(ranges)
        shell.log(f"edges settled into quiet: {moved} of {len(ranges)} ranges moved, {len(ranges) - len(settled)} joined")
        ranges = settled
    by_i = {w["i"]: w for w in words}
    for r in ranges:
        r["text"] = " ".join(by_i[i]["text"] for i in r["words"])
    retimed = core.tidy_text(core.retime(words, ranges), plan.get("retext"))
    edl = {"source": info["path"], "fps": info["fps"], "width": info["width"], "height": info["height"],
           "duration": info["duration"], "settings": settings, "ranges": ranges, "total": core.total(ranges), "words_out": retimed}
    d = Path(a.dir)
    (d / "edl.json").write_text(json.dumps(edl, indent=1), encoding="utf-8")
    (d / "edl.md").write_text(core.edl_markdown(words, ranges, plan.get("drop", []), info["duration"], f"Cut list: {Path(a.src).name}"), encoding="utf-8")
    shell.log(f"{info['duration']:.1f} s -> {edl['total']:.1f} s in {len(ranges)} pieces -> {d / 'edl.md'}")


if __name__ == "__main__":
    main()
