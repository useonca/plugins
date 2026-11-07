"""Pure decisions for the video map: what Claude reads before planning an edit.

No files, no subprocesses: map.py runs ffmpeg, ffprobe and scenedetect and hands the results here.
The map is the packed transcript with scene markers woven in, plus keyframes, silences, freezes and loudness.
"""

from __future__ import annotations

from pathlib import PurePath

import core

PER_SHEET = 28  # tiles per contact sheet: 7 columns, 4 rows


def parse_keyframes(csv_text: str) -> list[float]:
    """ffprobe `-show_entries frame=pts_time -of csv` lines (`frame,12.345`) -> sorted unique times; `N/A` skipped."""
    out = set()
    for line in csv_text.splitlines():
        for cell in line.split(","):
            cell = cell.strip()
            if cell and cell != "frame":
                try:
                    out.add(round(float(cell), 3))
                except ValueError:
                    pass
    return sorted(out)


def scene_sheets(scenes: list[dict], duration: float, per_sheet: int = PER_SHEET) -> list[dict]:
    """One entry per scene with its midpoint `t` (the sheet frame) and its 1-based sheet and tile.
    No scenes -> one scene over the whole video."""
    scenes = scenes or [{"start": 0.0, "end": duration}]
    out = []
    for k, s in enumerate(scenes):
        start, end = round(float(s["start"]), 3), round(float(s["end"]), 3)
        out.append({"scene": k + 1, "start": start, "end": end, "t": round((start + end) / 2, 3),
                    "sheet": k // per_sheet + 1, "tile": k % per_sheet + 1})
    return out


def _scene_at(sheets: list[dict], t: float) -> int:
    for s in sheets:
        if s["start"] <= t < s["end"]:
            return s["scene"]
    return sheets[-1]["scene"] if t >= sheets[-1]["start"] else sheets[0]["scene"]


def build_map(probe: dict, words: list[dict], silences: list[dict], scenes: list[dict], keyframes: list[float],
              freezes: list[dict], loudness: dict) -> dict:
    """Everything known about one source, as plain values (map.json)."""
    duration = probe["duration"]
    sheets = scene_sheets(scenes, duration)
    phrases = []
    for ph in core.phrases(words):
        phrases.append({"start": ph[0]["start"], "end": ph[-1]["end"], "first": ph[0]["i"], "last": ph[-1]["i"],
                        "text": core.phrase_text(ph), "scene": _scene_at(sheets, ph[0]["start"])})
    span = (words[-1]["end"] - words[0]["start"]) if words else 0.0
    gaps = [b - a for a, b in zip(keyframes, keyframes[1:])]
    stats = {
        "words": len(words),
        "wpm": round(len(words) / (span / 60), 1) if span > 0 else 0,
        "pause_total": round(sum(s.get("dur", s["end"] - s["start"]) for s in silences), 3),
        "filler_count": sum(1 for w in words if core.is_hard_filler(w["text"])),
        "keyframe_gap_max": round(max(gaps), 3) if gaps else None,
    }
    return {
        "source": probe["path"], "duration": duration, "size": f"{probe['width']}x{probe['height']}", "fps": probe["fps"],
        "phrases": phrases, "scenes": sheets, "keyframes": list(keyframes), "silences": silences, "freezes": freezes,
        "loudness": loudness, "repeats": core.repeated_runs(words), "stats": stats,
    }


def _marker(s: dict) -> str:
    return f"== scene {s['scene']} at {s['start']:.2f} s (sheet {s['sheet']}, tile {s['tile']}) =="


def map_markdown(m: dict) -> str:
    """map.md: phrases with scene markers in time order, repeated takes, then the stats."""
    name = PurePath(m["source"]).name
    out = [f"# Video map: {name} ({m['duration']:.1f} s)", "",
           f"{m['size']} at {m['fps']} fps. Each line is a phrase: `[start-end] #first-#last text`; the word indices go into "
           "plan.json. {braces} = hard filler. A scene marker names its tile on the contact sheets in `sheets/` "
           "(read left to right, top to bottom, 7 per row).", ""]
    scenes = list(m["scenes"])
    prev_end = None
    for p in m["phrases"]:
        while scenes and scenes[0]["start"] <= p["start"]:
            out.append(_marker(scenes.pop(0)))
        if prev_end is not None and p["start"] - prev_end >= 0.5:
            out.append(f"    ... pause {p['start'] - prev_end:.2f} s")
        out.append(f"[{p['start']:07.2f}-{p['end']:07.2f}] #{p['first']}-#{p['last']} {p['text']}")
        prev_end = p["end"]
    out += [_marker(s) for s in scenes]
    out += ["", "## Said twice (pick one take)", ""]
    out += [f"- #{r['first'][0]}-#{r['first'][1]} again at #{r['again'][0]}-#{r['again'][1]}" for r in m["repeats"]] or ["- none"]
    s, loud = m["stats"], m.get("loudness") or {}
    gap = f"{s['keyframe_gap_max']:.2f} s" if s["keyframe_gap_max"] is not None else "unknown"
    out += ["", "## Stats", "",
            f"- words: {s['words']} ({s['wpm']} per minute)",
            f"- pauses: {s['pause_total']:.2f} s in {len(m['silences'])} silences",
            f"- hard fillers: {s['filler_count']}",
            f"- scenes: {len(m['scenes'])}; freezes: {len(m['freezes'])}",
            f"- keyframe gap max: {gap} (a smart cut copies only between keyframes)",
            f"- loudness: {loud.get('I')} LUFS integrated, LRA {loud.get('LRA')}, peak {loud.get('TP')}"]
    return "\n".join(out) + "\n"
