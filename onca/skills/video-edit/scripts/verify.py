#!/usr/bin/env python3
"""Self-check a rendered video before the founder sees it or it is saved anywhere.

usage: verify.py FINAL.mp4 (--edl EDIT_DIR/edl.json | --timeline TL.json [--output NAME]) --dir VERIFY_DIR
                 [--fix WRONG=RIGHT ...] [--lufs -16] [--max-still 3.0]

1. Re-transcribes the output and diffs it against the approved words (edl.json words_out, or the
   timeline's kept words).
2. Checks the words on both sides of every cut are heard near the cut (nothing clipped).
3. Measures loudness (integrated LUFS, true peak) and the duration against the plan.
4. Finds black stretches (0.5 s or more), frozen picture (1 s or more) and stretches with no visible
   change longer than --max-still, or 12 s while someone talks through it (a viewer leaves).
5. `edges`: the sound in the 20 ms just inside every cut (from the source's own audio): sound within 15 dB
   of speech there is a word clipped at its start or end, which a re-transcript still hears.
6. With --timeline: overlays under the caption band while captions show (`covered`), the full cutaways
   captions sit over (look at those frames: is anything important under the caption?), and `zoom`: a zoom
   change mid-sentence or under 4 s after the last one.
7. Writes a 14-frame contact sheet: open it and look before reporting.
Writes VERIFY_DIR/verify.md and verify.json; exit code 0 even on warnings (Claude judges).
"""
import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import core, shell, timeline  # noqa: E402
import timeline_core as tlc  # noqa: E402

SCENE_CHANGE = 0.015  # ffmpeg scene score that counts as a visible change


def picture_checks(final: str, duration: float, max_still: float, speech: list) -> dict:
    """Loudness, black, frozen and still stretches, from one decode."""
    log = shell.ffmpeg_log(["-i", final, "-vf",
                            f"blackdetect=d=0.5,freezedetect=n=-60dB:d=1,select='gt(scene\\,{SCENE_CHANGE})',showinfo",
                            "-af", "ebur128=peak=true"])
    return {"blacks": core.parse_blacks(log), "freezes": core.parse_freezes(log), "loudness": core.parse_ebur128(log),
            "stills": core.still_stretches(core.parse_change_times(log), duration, max_still, speech)}


def plan_from(a, info: dict) -> dict:
    """What the output should hold: words, cut points, length, and (timeline) caption overlaps."""
    if a.edl:
        edl = json.loads(Path(a.edl).read_text())
        return {"words": edl["words_out"], "ranges": edl["ranges"], "total": edl["total"], "overlaps": None, "tl": None,
                "main": [{"src": "main", "in": r["start"], "out": r["end"]} for r in edl["ranges"]], "audio": {"main": edl["source"]}}
    tl = timeline.load(a.timeline)
    _durations, probes, problems = timeline.check(tl)
    timeline.fail_on(problems)
    size = f"{info['width']}x{info['height']}"
    output = next((o for o in tl["outputs"] if o["name"] == a.output), None) if a.output else \
        next((o for o in tl["outputs"] if o["size"] == size), None)
    if output is None:
        print(f"verify: no output {a.output or size} in the timeline", file=sys.stderr)
        raise SystemExit(2)
    words = timeline.words_of(tl) if tl.get("captions") else []
    ranges = [{"out_start": a_} for a_, _b, _c in tlc.main_spans(tl)]
    overlaps = []
    if words:
        groups = core.caption_groups(words, max_words=int(tl["captions"].get("max_words", 4)))
        sizes = {k: (p["width"], p["height"]) for k, p in probes.items() if p.get("width")}
        overlaps = tlc.caption_overlaps(tl, output, groups, sizes)
    subst = tl.get("audio_from") or {}
    audio = {c["src"]: tl["sources"][subst.get(c["src"], c["src"])] for c in tl["main"]}
    return {"words": words, "ranges": ranges, "total": tlc.main_length(tl), "overlaps": overlaps,
            "tl": tl, "main": tl["main"], "audio": audio}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("final")
    plan_arg = ap.add_mutually_exclusive_group(required=True)
    plan_arg.add_argument("--edl")
    plan_arg.add_argument("--timeline")
    ap.add_argument("--output", help="the timeline output this file is (default: the one with its size)")
    ap.add_argument("--dir", required=True)
    ap.add_argument("--fix", action="append", default=[])
    ap.add_argument("--lufs", type=float, default=-16.0)
    ap.add_argument("--max-still", type=float, default=3.0)
    a = ap.parse_args()
    d = Path(a.dir)
    d.mkdir(parents=True, exist_ok=True)
    info = shell.probe(a.final)
    plan = plan_from(a, info)
    shell.extract_wav(a.final, d / "final16k.wav")
    heard = core.apply_fixes(core.words_from_parakeet(shell.parakeet_json(d / "final16k.wav", d)), core.parse_fixes(a.fix))
    expected = [w["text"] for w in plan["words"]]
    diff = core.word_diff(expected, [w["text"] for w in heard])
    acc = core.word_accuracy(expected, [w["text"] for w in heard])
    clipped = core.clipped_at_cuts(core.boundary_words(plan["words"], plan["ranges"]), heard)
    spoken = plan["words"] or heard  # a timeline without captions: what the re-transcript heard, on the same clock
    zoom = tlc.zoom_problems(plan["tl"], spoken) if plan["tl"] else None
    pic = picture_checks(a.final, info["duration"], a.max_still, [(w["start"], w["end"]) for w in spoken])
    levels = {src: shell.levels(path) for src, path in plan["audio"].items()}
    edges = core.loud_edges(core.cut_edges(plan["main"]), levels, {k: core.clip_floor(v) for k, v in levels.items()})
    loud = pic["loudness"]
    sheet = d / "contact-final.png"
    shell.contact_sheet(a.final, core.sheet_times(info["duration"], 14), sheet)
    covered = [o for o in plan["overlaps"] or [] if o["kind"] != "full"]
    look = [o for o in plan["overlaps"] or [] if o["kind"] == "full"]
    checks = {
        "words": "ok" if acc >= 0.95 else "warn",
        "cuts": "ok" if not clipped else "warn",
        "loudness": "ok" if loud["I"] is not None and abs(loud["I"] - a.lufs) <= 1.0 and (loud["TP"] or 0) <= -1.0 else "warn",
        "duration": "ok" if abs(info["duration"] - plan["total"]) <= 0.15 else "warn",
        "black": "ok" if not pic["blacks"] else "warn",
        "freeze": "ok" if not pic["freezes"] else "warn",
        "still": "ok" if not pic["stills"] else "warn",
        "edges": "ok" if not edges else "warn",
    }
    if zoom is not None:
        checks["zoom"] = "ok" if not zoom else "warn"
    if plan["overlaps"] is not None:
        checks["covered"] = "ok" if not covered else "warn"
    res = {"checks": checks, "accuracy": acc, "diff": diff, "clipped": clipped, "loudness": loud,
           "duration": info["duration"], "planned": plan["total"], "size": f"{info['width']}x{info['height']}", "sheet": str(sheet),
           **pic, "edges": edges, "zoom": zoom, "covered": covered, "look": look, "heard": " ".join(w["text"] for w in heard)}
    (d / "verify.json").write_text(json.dumps(res, indent=1))
    spans = lambda xs: ", ".join(f"{x['start']:.1f}-{x['end']:.1f} s" for x in xs) or "none"  # noqa: E731
    md = [f"# Self-check: {Path(a.final).name}", "",
          f"- words: {checks['words']} ({acc:.0%} of the approved words heard, {len(diff)} differences)",
          f"- cuts: {checks['cuts']} ({len(plan['ranges']) - 1} cuts, {len(clipped)} with a word not heard next to it)",
          f"- loudness: {checks['loudness']} ({loud['I']} LUFS integrated, true peak {loud['TP']} dBFS, target {a.lufs})",
          f"- duration: {checks['duration']} ({info['duration']:.2f} s, planned {plan['total']:.2f} s, {info['width']}x{info['height']})",
          f"- black: {checks['black']} ({spans(pic['blacks'])})",
          f"- freeze: {checks['freeze']} ({spans(pic['freezes'])})",
          f"- still: {checks['still']} (no visible change for over {a.max_still:g} s, or 12 s while someone talks: {spans(pic['stills'])})",
          f"- edges: {checks['edges']} (a cut with sound right at its edge, a clipped word: "
          + (", ".join(f"{x['at']:.2f} s ({x['side']}, {x['over_db']} dB over quiet)" for x in edges) or "none") + ")"]
    if "zoom" in checks:
        md.append(f"- zoom: {checks['zoom']} (a zoom jump while someone talks: "
                  + ("; ".join(f"{x['at']:.2f} s {x['why']}" for x in zoom) or "none") + ")")
    if "covered" in checks:
        md.append(f"- covered: {checks['covered']} (an overlay under the captions: "
                  + (", ".join(f"{o['src']} {o['start']:.1f}-{o['end']:.1f} s" for o in covered) or "none") + ")")
        md.append("- look: captions over a full cutaway at " + (spans(look) if look else "no time")
                  + " (check nothing important sits under the caption band)")
    md += [f"- frames: {sheet} (look at it)", "", "## Differences (expected -> heard)", ""]
    md += [f"- {x['op']}: \"{x['expected']}\" -> \"{x['got']}\"" for x in diff] or ["- none"]
    md += ["", "## Cuts with a word not heard nearby", ""]
    md += [f"- cut {c['cut']} at {c['at']:.2f} s: {', '.join(c['missing'])}" for c in clipped] or ["- none"]
    md += ["", "## Heard", "", res["heard"]]
    (d / "verify.md").write_text("\n".join(md) + "\n")
    shell.log(" | ".join(f"{k} {v}" for k, v in checks.items()) + f" -> {d / 'verify.md'}")


if __name__ == "__main__":
    main()
