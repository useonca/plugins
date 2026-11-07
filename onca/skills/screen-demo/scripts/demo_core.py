"""The pure half of demo.py: a long demo's storyboard (demo.json) to a timeline, YouTube chapters and captions.

YouTube's chapter rules (Help 9884579): the first at 0:00, at least 3, each at least 10 s, in ascending
order. Captions upload as .srt or .vtt (Help 2734698).
"""

from __future__ import annotations

import re

DASHES = ("\u2014", "\u2013")
ID_RE = re.compile(r"^[a-z0-9-]+$")
SAY_MAX = 600
MIN_SCENE = 2.0
MIN_CHAPTER = 10.0


def _strings(v):
    if isinstance(v, str):
        yield v
    elif isinstance(v, dict):
        for x in v.values():
            yield from _strings(x)
    elif isinstance(v, list):
        for x in v:
            yield from _strings(x)


def storyboard_problems(sb: dict) -> list[str]:
    """Every problem of a storyboard, one line each; empty when it can be built."""
    if not isinstance(sb, dict):
        return ["the storyboard must be an object"]
    out = []
    chapters = sb.get("chapters")
    if not (isinstance(sb.get("title"), str) and sb["title"].strip()):
        out.append("the storyboard has no title")
    if not isinstance(chapters, list) or not chapters:
        out.append("the storyboard has no chapters")
        chapters = []
    if "tone" in sb and sb["tone"] not in FONT_PAIRS:
        out.append(f"tone must be one of {', '.join(FONT_PAIRS)}, not {sb['tone']!r}")
    fonts = sb.get("fonts")
    if fonts is not None and not (isinstance(fonts, dict) and all(isinstance(v, str) and v.strip() and v.strip().lower() not in FORBIDDEN_FONTS
                                                                  for v in fonts.values())):
        out.append("fonts is {\"display\": name, \"text\": name} with real font names (not a system default or Arial)")
    if "size" in sb and not re.fullmatch(r"\d+x\d+", str(sb["size"])):
        out.append("size must be WIDTHxHEIGHT, like 1920x1080")
    seen = set()
    for ci, ch in enumerate(chapters, 1):
        if not isinstance(ch, dict):
            out.append(f"chapter {ci} must be an object")
            continue
        if not (isinstance(ch.get("title"), str) and ch["title"].strip()):
            out.append(f"chapter {ci} has no title")
        scenes = ch.get("scenes")
        if not isinstance(scenes, list) or not scenes:
            out.append(f"chapter {ci} has no scenes")
            continue
        for scene in scenes:
            if not isinstance(scene, dict):
                out.append(f"chapter {ci}: a scene must be an object")
                continue
            sid = scene.get("id")
            if not (isinstance(sid, str) and ID_RE.match(sid)):
                out.append(f"scene id {sid!r} must be lowercase letters, digits and hyphens")
            elif sid in seen:
                out.append(f"duplicate scene id {sid!r}")
            seen.add(sid)
            if not scene.get("clip") and not scene.get("card"):
                out.append(f"scene {sid!r} has neither clip nor card")
            say = scene.get("say")
            if say is not None and not isinstance(say, str):
                out.append(f"scene {sid!r}: say must be text")
            elif say and len(say) > SAY_MAX:
                out.append(f"scene {sid!r}: say is {len(say)} characters, over {SAY_MAX}; split the scene")
            if "min" in scene and not (isinstance(scene["min"], (int, float)) and scene["min"] > 0):
                out.append(f"scene {sid!r}: min must be seconds above 0")
    if any(d in s for s in _strings(sb) for d in DASHES):
        out.append("the storyboard has an em or en dash; use a hyphen or a comma")
    return out


def _r(v: float) -> float:
    return round(v, 3)


def speaks(scene: dict) -> bool:
    """A scene has narration: words to say, or a WAV of its own at `audio` (any voice, used as is)."""
    return bool((scene.get("say") or "").strip() or scene.get("audio"))


def voice_path(scene: dict) -> str:
    """Where a spoken scene's WAV is, relative to the storyboard: its `audio`, else voice/<id>.wav."""
    return scene.get("audio") or f"voice/{scene['id']}.wav"


def timeline(sb: dict, voice: dict[str, float], pad: float = 0.35) -> list[dict]:
    """Scenes back to back. A voiced scene lasts its voice plus `pad` either side, at least its `min` (2 s);
    `voice` maps a scene id to its WAV's length in seconds."""
    out = []
    t = 0.0
    for ci, ch in enumerate(sb["chapters"]):
        for scene in ch["scenes"]:
            v = voice.get(scene["id"])
            floor = scene.get("min") or MIN_SCENE
            length = max(floor, v + 2 * pad) if v else floor
            voiced = bool(v)
            out.append({
                "id": scene["id"], "chapter": ch["title"], "chapter_index": ci,
                "start": _r(t), "end": _r(t + length),
                "voice_start": _r(t + pad) if voiced else None, "voice_end": _r(t + pad + v) if voiced else None,
                "say": scene.get("say"), "clip": scene.get("clip"), "clip_from": scene.get("clip_from", 0),
                "card": scene.get("card"),
                "audio": voice_path(scene) if voiced else None,
            })
            t = _r(t + length)
    return out


def chapter_marks(tl: list[dict]) -> list[dict]:
    """{t, title} where each chapter's first scene starts."""
    marks = []
    last = None
    for s in tl:
        key = s["chapter_index"]
        if key != last:
            marks.append({"t": s["start"], "title": s["chapter"]})
            last = key
    return marks


def yt_time(t: float) -> str:
    """YouTube's timestamp: 0:00, 1:05, 1:02:03."""
    total = int(t)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def chapter_problems(marks: list[dict], duration: float) -> list[str]:
    """What keeps YouTube from showing these chapters."""
    out = []
    if not marks or marks[0]["t"] != 0:
        out.append("the first chapter must start at 0:00")
    if len(marks) < 3:
        out.append(f"YouTube needs at least 3 chapters, this has {len(marks)}")
    for a, b in zip(marks, marks[1:]):
        if b["t"] <= a["t"]:
            out.append(f"chapter {b['title']!r} at {yt_time(b['t'])} is not after {a['title']!r}")
    for k, m in enumerate(marks):
        end = marks[k + 1]["t"] if k + 1 < len(marks) else duration
        length = end - m["t"]
        if 0 <= length < MIN_CHAPTER:
            out.append(f"chapter {m['title']!r} at {yt_time(m['t'])} lasts {length:.1f} s, under {MIN_CHAPTER:.0f} s")
    return out


def description(title: str, marks: list[dict]) -> str:
    """A YouTube description with its chapter lines."""
    return f"{title}\n\nChapters\n" + "".join(f"{yt_time(m['t'])} {m['title']}\n" for m in marks)


# ---------------------------------------------------------------- type

# Open-licence (OFL) pairings on Google Fonts for when the brand kit names no font: tone -> (display, text).
FONT_PAIRS = {
    "modern": ("Inter Tight", "Inter"),
    "friendly": ("Manrope", "Manrope"),
    "editorial": ("Fraunces", "Inter"),
    "technical": ("Space Grotesk", "Inter"),
    "warm": ("Plus Jakarta Sans", "Plus Jakarta Sans"),
}
DEFAULT_TONE = "modern"
FORBIDDEN_FONTS = {"arial", "helvetica", "sans-serif", "serif", "system-ui", "-apple-system", "times new roman"}


def fonts_for(sb: dict) -> dict:
    """{"display", "text"}: the storyboard's `fonts` (from the brand kit), else the pairing for its `tone`."""
    given = sb.get("fonts") if isinstance(sb.get("fonts"), dict) else {}
    display, text = FONT_PAIRS.get(sb.get("tone") or DEFAULT_TONE, FONT_PAIRS[DEFAULT_TONE])
    return {"display": given.get("display") or display, "text": given.get("text") or given.get("display") or text}


def smart_quotes(text: str) -> str:
    """Straight quotes to curly ones: an apostrophe or closing quote after a letter, an opening one elsewhere."""
    out = []
    for k, ch in enumerate(text):
        prev = text[k - 1] if k else " "
        if ch == "'":
            out.append("\u2019" if prev.isalnum() or prev in ".,!?" else "\u2018")
        elif ch == '"':
            out.append("\u201d" if prev.strip() and prev not in "([{" else "\u201c")
        else:
            out.append(ch)
    return "".join(out)


def no_orphan(text: str) -> str:
    """The last two words held together (a no-break space), so no line ends a title with one word alone."""
    words = text.split(" ")
    if len(words) < 3:
        return text
    return " ".join(words[:-2]) + " " + words[-2] + "\u00a0" + words[-1]


def balance_lines(text: str, max_chars: int) -> list[str]:
    """`text` broken into the fewest lines of at most `max_chars`, as even in length as possible, never ending
    on a line of one word when the text has more than one (what CSS `text-wrap: balance` does, for places that
    break lines themselves)."""
    words = text.split()
    if not words:
        return []
    n = len(_wrap(text, max_chars))
    best = None

    def walk(start: int, lines: list[str]):
        nonlocal best
        if start == len(words):
            if len(lines) == n and (len(lines) == 1 or len(lines[-1].split()) > 1 or len(words) == 1):
                score = max(len(ln) for ln in lines) - min(len(ln) for ln in lines)
                if best is None or score < best[0]:
                    best = (score, list(lines))
            return
        if len(lines) >= n:
            return
        for end in range(start + 1, len(words) + 1):
            line = " ".join(words[start:end])
            if len(line) > max_chars and end > start + 1:
                break
            walk(end, lines + [line])

    walk(0, [])
    return best[1] if best else _wrap(text, max_chars)


def _wrap(text: str, max_chars: int) -> list[str]:
    lines, line = [], ""
    for word in text.split():
        while len(word) > max_chars:
            if line:
                lines.append(line)
                line = ""
            lines.append(word[:max_chars])
            word = word[max_chars:]
        if not line:
            line = word
        elif len(line) + 1 + len(word) <= max_chars:
            line += " " + word
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def _fits(text: str, max_chars: int) -> bool:
    return len(_wrap(text, max_chars)) <= 2


def _split(text: str, pattern: str) -> list[str]:
    return [p.strip() for p in re.split(pattern, text) if p.strip()]


def _chunks(text: str, max_chars: int) -> list[str]:
    """`text` in pieces of at most 2 lines: at sentence ends first, then commas, then spaces."""
    if _fits(text, max_chars):
        return [text]
    for pattern in (r"(?<=[.!?])\s+", r"(?<=[,;:])\s+"):
        parts = _split(text, pattern)
        if len(parts) > 1:
            out = []
            for part in parts:
                out += _chunks(part, max_chars)
            return _merge(out, max_chars)
    lines = _wrap(text, max_chars)
    return [" ".join(lines[k:k + 2]) for k in range(0, len(lines), 2)]


def _merge(pieces: list[str], max_chars: int) -> list[str]:
    """Join neighbouring short pieces while they still fit in 2 lines."""
    out: list[str] = []
    for p in pieces:
        if out and _fits(out[-1] + " " + p, max_chars) and not out[-1].endswith((".", "!", "?")):
            out[-1] += " " + p
        else:
            out.append(p)
    return out


def cues(tl: list[dict], max_chars: int = 42) -> list[dict]:
    """Caption cues {start, end, text} for every voiced scene: its `say` in pieces of at most 2 lines of
    `max_chars`, each timed in proportion to its characters inside the voice window."""
    out = []
    for s in tl:
        words = " ".join((s.get("say") or "").split())
        if not words or s.get("voice_start") is None:
            continue
        pieces = _chunks(words, max_chars)
        total = sum(len(p) for p in pieces)
        t, span = s["voice_start"], s["voice_end"] - s["voice_start"]
        for p in pieces:
            length = span * len(p) / total
            out.append({"start": _r(t), "end": _r(t + length), "text": "\n".join(balance_lines(smart_quotes(p), max_chars))})
            t += length
    return out


def _stamp(t: float, sep: str) -> str:
    ms = int(round(t * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def srt(cue_list: list[dict]) -> str:
    return "".join(f"{k}\n{_stamp(c['start'], ',')} --> {_stamp(c['end'], ',')}\n{c['text']}\n\n"
                   for k, c in enumerate(cue_list, 1))


def vtt(cue_list: list[dict]) -> str:
    return "WEBVTT\n\n" + "".join(f"{_stamp(c['start'], '.')} --> {_stamp(c['end'], '.')}\n{c['text']}\n\n" for c in cue_list)
