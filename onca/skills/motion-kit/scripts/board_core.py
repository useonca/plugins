"""A board: the reel's storyboard, one beat per spoken phrase, each naming its scene type, what it shows, the
story elements that act the line out, its keyword, tone, scene change and presenter place. Pure: beats from the
voice's words, validation, the pace rules, the page and cues skeleton, the render's pace report and the beat
sheet's times. kit.py is the only shell."""

from __future__ import annotations

import html as _html
import json
import re

import kit_core
from presenter_core import placement

VERSION = 1
RULES = ("thin-beat", "thin-motion", "beat-short", "beat-long", "hook-late", "scene-repeat", "tone-stuck",
         "cut-heavy", "no-keyword", "no-closure")
WARN_ONLY = ("no-keyword",)
MIN_BEAT = 1.0  # the lint's floor; beats_from_words aims for 1.2
MAX_BEAT = 3.0
HOOK_MAX = 2.5
TONE_MAX = 12.0  # seconds without a tone switch, in videos over LONG_VIDEO
LONG_VIDEO = 15.0
MIN_ELEMENTS = 2
UNCOUNTED_PARTS = ("captions", "drift", "scene")  # what moves in every beat anyway
TEXTURES = ("grid", "dots", "plain")
TONES = ("light", "dark")
TRANSITIONS = ("cut", "slide", "whip", "tear", "focus", "zoom", "fade")
PRESENTERS = ("off", "bottom", "full", "corner")
CLOSERS = ("end", "headline")
HEADLINES = ("headline",)  # scenes whose big type says the line: the captions step aside (unless the presenter fills the frame)
BEAT_ID = re.compile(r"[A-Za-z0-9_]+")  # no "-": a cue id is <beat>-<name>
SLOT = re.compile(r"\{\{([A-Za-z0-9_-]+)\}\}")
END_PAD = 0.4  # the last beat holds this long after its last word
BEAT_DEFAULTS = {"say": "", "scene": "", "visual": "", "elements": [], "keyword": "", "emoji": "", "tone": "light",
                 "transition": "cut", "presenter": "off", "waive": {}}
TEXT_KEYS = ("say", "scene", "visual", "keyword", "emoji")
KEYWORD_OFFSET = "keyword+0.25"
PRESENTER_MOVE = 0.5
# Placeholders that let a cue whose param is still a {{slot}} be checked for everything else.
SLOT_PLACEHOLDERS = {"to": 100, "values": [1, 2, 3, 4]}


def _r(t: float) -> float:
    return round(t, 3)


# ---------------------------------------------------------------- beats from the voice


def _phrases(words: list) -> list:
    """(sentence number, words) per phrase: video-edit's caption grouping inside each line and sentence."""
    out = []
    for k, run in enumerate(kit_core._runs(words)):
        out += [(k, g["words"]) for g in kit_core.edit_core.caption_groups(run, kit_core.REEL_MAX_WORDS, kit_core.REEL_MAX_CHARS)]
    return out


def _lengths(groups: list, end: float) -> list:
    starts = [g[1][0]["start"] for g in groups]
    return [(starts[i + 1] if i + 1 < len(starts) else end) - starts[i] for i in range(len(starts))]


def _join_short(groups: list, end: float, min_s: float) -> list:
    """Each phrase under min_s joins its shorter neighbour in the same sentence (a lone short sentence stays)."""
    groups = list(groups)
    while True:
        lens = _lengths(groups, end)
        for i, (sent, ws) in enumerate(groups):
            if lens[i] >= min_s:
                continue
            near = [j for j in (i - 1, i + 1) if 0 <= j < len(groups) and groups[j][0] == sent]
            if not near:
                continue
            j = min(near, key=lambda n: lens[n])
            a, b = min(i, j), max(i, j)
            groups[a:b + 1] = [(sent, groups[a][1] + groups[b][1])]
            break
        else:
            return groups


def _split_long(ws: list, until: float, min_s: float, max_s: float) -> list:
    """A phrase over max_s cut at its widest word gap (one leaving both sides min_s or more, when there is one),
    again until every piece fits."""
    if until - ws[0]["start"] <= max_s or len(ws) < 2:
        return [ws]
    cuts = range(1, len(ws))
    fair = [k for k in cuts if ws[k]["start"] - ws[0]["start"] >= min_s and until - ws[k]["start"] >= min_s]
    k = max(fair or cuts, key=lambda n: (ws[n]["start"] - ws[n - 1]["end"], -abs(n - len(ws) / 2)))
    return _split_long(ws[:k], ws[k]["start"], min_s, max_s) + _split_long(ws[k:], until, min_s, max_s)


def beats_from_words(words: list, min_s: float = 1.2, max_s: float = 3.0) -> list:
    """[{id, from, to, say}]: one beat per spoken phrase, tiling the speech: `from` is the first word's start,
    `to` the next beat's `from` (the last one ends END_PAD after the last word)."""
    words = sorted((w for w in words if isinstance(w, dict) and str(w.get("text", "")).strip()), key=lambda w: w["start"])
    if not words:
        return []
    end = words[-1]["end"] + END_PAD
    groups = _join_short(_phrases(words), end, min_s)
    pieces = []
    for i, (_, ws) in enumerate(groups):
        until = groups[i + 1][1][0]["start"] if i + 1 < len(groups) else end
        pieces += _split_long(ws, until, min_s, max_s)
    beats = []
    for i, ws in enumerate(pieces):
        to = pieces[i + 1][0]["start"] if i + 1 < len(pieces) else end
        beats.append({"id": f"b{i + 1}", "from": _r(ws[0]["start"]), "to": _r(to),
                      "say": " ".join(str(w["text"]).strip() for w in ws)})
    return beats


def new_board(words: list, size: list, fps: int, texture: str = "grid") -> dict:
    """A valid board from the voice's words; the client then fills each beat's scene, visual, elements, keyword,
    tone and scene change."""
    beats = [beat(b) for b in beats_from_words(words)]
    return {"version": VERSION, "size": list(size), "fps": fps, "style": "reel", "words": "words.json",
            "ground": {"texture": texture}, "beats": beats}


def beat(b: dict) -> dict:
    """A beat with every optional key at its default."""
    return dict(json.loads(json.dumps(BEAT_DEFAULTS)), **b)


# ---------------------------------------------------------------- validation


def validate(board, scene_types: set) -> list:
    """Every structural problem with a board, all at once (an empty scene is allowed: not picked yet)."""
    if not isinstance(board, dict):
        return ["board.json must be a JSON object"]
    problems = []
    if board.get("version") != VERSION:
        problems.append(f"version must be {VERSION}, got {board.get('version')!r}")
    size = board.get("size")
    if not (isinstance(size, list) and len(size) == 2 and all(isinstance(n, int) and not isinstance(n, bool) and n > 0 for n in size)):
        problems.append(f"size must be [width, height] in pixels, got {size!r}")
    fps = board.get("fps")
    if not isinstance(fps, int) or isinstance(fps, bool) or fps <= 0:
        problems.append(f"fps must be a whole number over 0, got {fps!r}")
    if "words" in board and not isinstance(board["words"], str):
        problems.append("words must be the path of a words.json file")
    ground = board.get("ground", {})
    if not isinstance(ground, dict) or ground.get("texture", "grid") not in TEXTURES:
        problems.append(f"ground.texture must be one of {', '.join(TEXTURES)}")
    beats = board.get("beats")
    if not isinstance(beats, list) or not beats:
        return problems + ["beats must list the video's beats (at least one)"]
    seen, last = set(), 0.0
    for k, b in enumerate(beats):
        if not isinstance(b, dict):
            problems.append(f"beats[{k}] must be an object")
            continue
        bid = b.get("id")
        where = f"beats[{k}] ({bid})" if isinstance(bid, str) else f"beats[{k}]"
        if not (isinstance(bid, str) and BEAT_ID.fullmatch(bid)):
            problems.append(f"{where}: id must be letters, digits or _")
        elif bid in seen:
            problems.append(f"{where}: id {bid!r} is used twice")
        seen.add(bid)
        a, z = b.get("from"), b.get("to")
        if not (kit_core._num(a) and kit_core._num(z) and 0 <= a < z):
            problems.append(f"{where}: needs from < to, in seconds")
        elif a < last - 1e-9:
            problems.append(f"{where}: starts at {a:g}, before the beat ahead of it ends")
        else:
            last = z
        for key in TEXT_KEYS:
            if key in b and not isinstance(b[key], str):
                problems.append(f"{where}: {key} must be text")
        if isinstance(b.get("keyword"), str) and len(b["keyword"].split()) > 1:
            problems.append(f"{where}: keyword must be one word of the line (the caption boxes one word), got {b['keyword']!r}")
        if isinstance(b.get("scene"), str) and b["scene"] and b["scene"] not in scene_types:
            problems.append(f"{where}: unknown scene {b['scene']!r} (one of {', '.join(sorted(scene_types))})")
        if "elements" in b and not (isinstance(b["elements"], list) and all(isinstance(e, str) and e.strip() for e in b["elements"])):
            problems.append(f"{where}: elements must list the story elements as text")
        for key, allowed in (("tone", TONES), ("transition", TRANSITIONS), ("presenter", PRESENTERS)):
            if key in b and b[key] not in allowed:
                problems.append(f"{where}: {key} must be one of {', '.join(allowed)}, got {b[key]!r}")
        waive = b.get("waive", {})
        if not isinstance(waive, dict):
            problems.append(f"{where}: waive must be an object of rule: reason")
        else:
            for rule, why in waive.items():
                if rule not in RULES:
                    problems.append(f"{where}: waive names unknown rule {rule!r} (one of {', '.join(RULES)})")
                elif not (isinstance(why, str) and why.strip()):
                    problems.append(f"{where}: waive.{rule} needs the reason")
    return problems


def unfinished(board: dict) -> list:
    """The beats the client has not picked a scene type for yet."""
    return [f"{b['id']}: no scene type yet" for b in board["beats"] if not beat(b)["scene"]]


# ---------------------------------------------------------------- pace


def pace(board: dict, cues=None) -> list:
    """[{rule, beat, message, waived}] for every breach of the pace rules, in beat order. With `cues` (cues.json's
    cues, word times resolved), also each beat with fewer than MIN_ELEMENTS distinct animated elements."""
    beats = [beat(b) for b in board["beats"]]
    out = []

    def add(rule: str, b: dict, message: str, anywhere: bool = False) -> None:
        owner = b if rule in b["waive"] else next((x for x in beats if rule in x["waive"]), None) if anywhere else None
        out.append({"rule": rule, "beat": b["id"], "message": message, "waived": owner is not None,
                    "because": owner["waive"][rule] if owner else ""})

    length = beats[-1]["to"]
    for i, b in enumerate(beats):
        dur = b["to"] - b["from"]
        if len(b["elements"]) < MIN_ELEMENTS:
            add("thin-beat", b, f"{b['id']}: {len(b['elements'])} story element(s); act the line out with "
                                f"{MIN_ELEMENTS} or more animated pieces")
        if isinstance(cues, list):
            moving = {c.get("id") for c in cues if isinstance(c, dict) and c.get("part") not in UNCOUNTED_PARTS
                      and kit_core._num(c.get("at")) and b["from"] - 1e-9 <= c["at"] < b["to"] - 1e-9}
            if len(moving) < MIN_ELEMENTS:
                add("thin-motion", b, f"{b['id']}: {len(moving)} animated element(s) in cues.json; give it "
                                      f"{MIN_ELEMENTS} or more (captions, drift and scene changes do not count)")
        if dur < MIN_BEAT - 1e-9:
            add("beat-short", b, f"{b['id']}: {dur:.2f} s, under {MIN_BEAT:g} s")
        if dur > MAX_BEAT + 1e-9:
            add("beat-long", b, f"{b['id']}: {dur:.2f} s, over {MAX_BEAT:g} s; split it or change the picture inside it")
        if i == 0 and b["to"] > HOOK_MAX + 1e-9:
            add("hook-late", b, f"{b['id']}: the hook ends at {b['to']:g} s; the first picture changes by {HOOK_MAX:g} s")
        if i >= 2 and b["scene"] and beats[i - 1]["scene"] == beats[i - 2]["scene"] == b["scene"]:
            add("scene-repeat", b, f"{b['id']}: scene {b['scene']!r} three beats in a row")
        if b["say"].strip() and not b["keyword"].strip():
            add("no-keyword", b, f"{b['id']}: no keyword (the caption's boxed word)")
    if length > LONG_VIDEO:
        start = 0
        for i in range(1, len(beats) + 1):
            if i == len(beats) or beats[i]["tone"] != beats[start]["tone"]:
                span = beats[i - 1]["to"] - beats[start]["from"]
                if span > TONE_MAX + 1e-9:
                    add("tone-stuck", beats[start], f"{beats[start]['id']}: {beats[start]['tone']} for {span:.1f} s from "
                                                    f"here; switch tone (dark and light) at least every {TONE_MAX:g} s")
                start = i
    changes = [b["transition"] for b in beats[1:]]
    if changes:
        cuts = changes.count("cut")
        if cuts * 3 > len(changes):
            add("cut-heavy", beats[1], f"{cuts} of {len(changes)} scene changes are cuts; at most a third", anywhere=True)
        elif length > LONG_VIDEO and len(set(changes)) < 3:
            add("cut-heavy", beats[1], f"only {len(set(changes))} kind(s) of scene change; use 3 or more", anywhere=True)
    if beats[-1]["scene"] not in CLOSERS:
        add("no-closure", beats[-1], f"{beats[-1]['id']}: the last beat is {beats[-1]['scene'] or 'unpicked'!r}; "
                                     f"close on {' or '.join(CLOSERS)}")
    order = {b["id"]: k for k, b in enumerate(beats)}
    return sorted(out, key=lambda f: order[f["beat"]])


def failing(found: list) -> list:
    """The breaches that fail a check: not waived, not a warning."""
    return [f for f in found if not f["waived"] and f["rule"] not in WARN_ONLY]


# ---------------------------------------------------------------- presenter moves


def _presenter_cues(beats: list, size: list) -> list:
    out, prev = [], "off"
    for k, b in enumerate(beats):
        now = b["presenter"]
        if now == prev:
            continue
        box = placement(now if now != "off" else prev, size)
        to = dict(box, opacity=0 if now == "off" else 1)
        if k == 0:  # placed from the first frame
            frm = dict(to)
        elif prev == "off":
            frm = dict(box, opacity=0)
        else:
            frm = dict(placement(prev, size), opacity=1)
        out.append({"id": "presenter", "part": "move", "at": b["from"], "dur": PRESENTER_MOVE,
                    "params": {"from": frm, "to": to, "ease": "outQuint"}})
        prev = now
    return out


# ---------------------------------------------------------------- the skeleton


def _keyword_at(b: dict, words: list) -> float:
    key = kit_core._norm(b["keyword"])
    for w in words:
        if key and b["from"] - 1e-9 <= w["start"] < b["to"] and kit_core._norm(w["text"]) == key:
            return w["start"] + 0.25
    return b["from"] + 0.25


def _fill(text: str, b: dict) -> str:
    def one(m):
        name = m.group(1)
        if name == "id":
            return b["id"]
        if name in ("say", "keyword"):
            return _html.escape(b[name], quote=True)
        return m.group(0)
    return SLOT.sub(one, text)


def _stage(scene: dict) -> str:
    return scene.get("html") or '<div id="{{id}}-stage" class="om-stage"></div>'


def _fill_value(v, b: dict):
    """A cue's params with id, say and keyword filled as plain text (the page's copy is HTML-escaped, this is not)."""
    if isinstance(v, str):
        return SLOT.sub(lambda m: b[m.group(1)] if m.group(1) in ("id", "say", "keyword") else m.group(0), v)
    if isinstance(v, list):
        return [_fill_value(x, b) for x in v]
    if isinstance(v, dict):
        return {k: _fill_value(x, b) for k, x in v.items()}
    return v


def _scene_cues(b: dict, scene: dict, words: list) -> list:
    out = []
    for c in scene.get("cues") or []:
        cue = _fill_value(c, b)
        cue["id"] = b["id"] + cue["id"][1:] if cue["id"].startswith("@") else cue["id"]
        at = _keyword_at(b, words) if cue["at"] == KEYWORD_OFFSET else b["from"] + cue["at"]
        cue["at"] = _r(at)
        if kit_core.voiced(cue) and "dur" not in cue:  # its words are this beat's only
            cue["dur"] = _r(max(0.1, b["to"] - at))
        out.append(cue)
    return out


def skeleton(board: dict, scenes: dict, words: list) -> tuple:
    """(sections_html, cues doc) for a checked board: one scene section per beat holding its template with id, say
    and keyword filled (the visual as a comment for the client), and the cues: each template's default cues at its
    beat, a scene change into every beat after the first, a drift on every beat's stage, the reel captions and the
    presenter's moves. Raises ValueError naming every problem."""
    problems = validate(board, set(scenes))
    if not problems:
        problems = unfinished(board)
    if problems:
        raise ValueError("; ".join(problems))
    beats = [beat(b) for b in board["beats"]]
    texture = (board.get("ground") or {}).get("texture", "grid")
    sections, cues = [], []
    for k, b in enumerate(beats):
        scene = scenes[b["scene"]]
        visual = b["visual"].replace("--", "- -")
        sections.append(
            f'<section id="{b["id"]}" class="om-scene" data-scene="{b["scene"]}" data-tone="{b["tone"]}" '
            f'data-presenter="{b["presenter"]}">\n'
            f'  <!-- {b["id"]}: {visual} | elements: {", ".join(b["elements"]).replace("--", "- -")} -->\n'
            f'  <div class="om-ground" data-texture="{texture}"></div>\n'
            f'  {_fill(_stage(scene), b).strip()}\n'
            f'</section>')
        if k:
            scene_cue = {"id": b["id"], "part": "scene", "at": b["from"],
                         "params": {"kind": b["transition"], "out": beats[k - 1]["id"]}}
            if b["transition"] == "cut":
                scene_cue["sfx"] = ["whoosh-short"]  # every scene change is heard
            cues.append(scene_cue)
        cues.append({"id": f"{b['id']}-stage", "part": "drift", "at": b["from"], "dur": _r(b["to"] - b["from"])})
        cues += _scene_cues(b, scene, words)
    cues.append({"id": "captions", "part": "captions", "at": 0,
                 "params": {"style": "reel", "breaks": [b["from"] for b in beats],
                            "keywords": [b["keyword"] for b in beats],
                            "tones": [b["tone"] for b in beats],
                            "hide": [b["scene"] in HEADLINES and b["presenter"] != "full" for b in beats],
                            "emoji": {b["keyword"]: b["emoji"] for b in beats if b["keyword"] and b["emoji"]}}})
    if any(b["presenter"] != "off" for b in beats):
        cues += _presenter_cues(beats, board["size"])
    cues.sort(key=lambda c: c["at"])
    doc = {"version": 1, "fps": board["fps"], "size": list(board["size"]), "duration": beats[-1]["to"],
           "words": board.get("words", "words.json"), "cues": cues}
    return "\n".join(sections) + "\n", doc


def slots_left(html: str, doc=None) -> list:
    """(slot, section) for each {{slot}} still in the page (the section around it) or in the cues (the beat its
    cue belongs to, from the cue id `<beat>-<name>`)."""
    out, section = [], "?"
    for line in html.splitlines():
        m = re.search(r'<section[^>]*\bid="([^"]+)"', line)
        if m:
            section = m.group(1)
        out += [(name, section) for name in SLOT.findall(line)]
    for c in (doc or {}).get("cues", []) if isinstance(doc, dict) else []:
        if isinstance(c, dict):
            where = str(c.get("id", "?")).split("-")[0]
            out += [(name, where) for name in SLOT.findall(json.dumps(c.get("params", {})))]
    return out


def with_placeholders(doc: dict) -> dict:
    """The cues doc with each param that is still a whole {{slot}} given a placeholder value, so everything else in
    it can be checked."""
    out = json.loads(json.dumps(doc))
    for c in out.get("cues", []):
        p = c.get("params")
        if isinstance(p, dict):
            for key, v in p.items():
                if isinstance(v, str) and SLOT.fullmatch(v):
                    p[key] = SLOT_PLACEHOLDERS.get(key, v)
    return out


# ---------------------------------------------------------------- the render


QUIET_SKIP = 0.3  # a beat's own scene change, at its start, is not a change inside it
PACE_FPS = 10  # frames a second compared
PACE_SIZE = (136, 240)  # grey frames this small: a slow drift moves nothing, a new element still shows
PIXEL_DELTA = 32  # a pixel changed when its grey level moves more than this
CHANGE_MIN = 0.002  # a visible change: this share of the pixels changed (an element entering is 0.004 or more,
                    # a talking presenter about 0.001, the drift 0)


def changed_fraction(a: bytes, b: bytes, delta: int = PIXEL_DELTA) -> float:
    """The share of pixels whose grey level moved more than delta between two frames of the same size."""
    if not a or len(a) != len(b):
        return 1.0
    return sum(1 for x, y in zip(a, b) if abs(x - y) > delta) / len(a)


def change_times(frames: list, fps: float = PACE_FPS, min_fraction: float = CHANGE_MIN) -> list:
    """The times (s) of the frames that differ visibly from the frame before them."""
    return [round(k / fps, 3) for k in range(1, len(frames)) if changed_fraction(frames[k - 1], frames[k]) > min_fraction]


def pace_report(change_times: list, duration: float, beats=None, max_still: float = 2.5) -> dict:
    """The render's shots (between visible changes), its stills over max_still, and the beats with no visible
    change inside them."""
    inside = sorted(t for t in change_times if 0 < t < duration)
    points = [0.0] + inside + [duration]
    gaps = [b - a for a, b in zip(points, points[1:]) if b > a]
    stills = kit_core.edit_core.still_stretches(inside, duration, max_still)
    quiet = []
    for b in beats or []:
        if not any(b["from"] + QUIET_SKIP <= t < b["to"] for t in inside):
            quiet.append(b["id"])
    shots = len(gaps)
    return {"shots": shots, "avg_shot": _r(duration / shots) if shots else _r(duration),
            "longest_still": _r(max(gaps) if gaps else duration), "stills": stills, "quiet_beats": quiet,
            "ok": not stills and not quiet}


def sheet_times(board: dict) -> list:
    """(beat id, its middle in seconds) for each beat: the frames of the beat sheet."""
    return [(b["id"], _r((b["from"] + b["to"]) / 2)) for b in board["beats"]]
