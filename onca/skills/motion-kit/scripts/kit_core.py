"""The motion kit's pure core: cues and brand validation, beat snapping, voice words, the platform plan and a
small PNG codec. No disk, no clock, no network: kit.py is the only shell.

The part table here mirrors assets/kit/motion.js; the events parity test keeps the two in step.
"""

from __future__ import annotations

import json
import math
import re
import struct
import sys
import zlib
from html.parser import HTMLParser
from pathlib import Path

_EDIT = Path(__file__).resolve().parents[2] / "video-edit" / "scripts"
if str(_EDIT) not in sys.path:
    sys.path.insert(0, str(_EDIT))
import core as edit_core  # noqa: E402  (video-edit's pure core: caption groups, levels)

VERSION = 1
PARTS = ("words", "highlight", "captions", "odometer", "card-grid", "pop", "drop", "move", "chart", "focus",
         "spotlight", "bubble", "morph", "scene")
SCENE_KINDS = ("cut", "slide", "whip", "tear")
SCENE_FROM = ("left", "right", "up", "down")
SFX = ("whoosh", "whoosh-short", "pop", "tick", "key", "typing", "sent", "received", "notification", "tap",
       "riser", "impact")
# Default lengths (seconds) of the parts whose sound depends on their length; motion.js holds the same numbers.
DUR = {"odometer": 1.4, "drop": 0.28, "move": 0.6, "focus": 0.6}
EASES = ("linear", "outCubic", "outQuart", "outExpo", "inCubic", "inOutQuad")
SNAPS = ("beat", "bar")
BEAT_CONFIDENCE = 0.5
HEX = re.compile(r"#[0-9A-Fa-f]{6}")
BRAND_DEFAULTS = {"ink": "#151412", "paper": "#F6F1E7", "accent": "#D99A0E", "accent_ink": "#151412",
                  "muted": "#8A8378", "display_font": "Inter", "body_font": "Inter", "label_font": "DM Serif Display",
                  "font_files": {}}
FONT_VARS = (("display_font", "--om-display", "Georgia, serif"), ("body_font", "--om-body", "system-ui, sans-serif"),
             ("label_font", "--om-label", "Georgia, serif"))
FONT_TOKENS = tuple(key for key, _, _ in FONT_VARS)
COLOURS = ("ink", "paper", "accent", "accent_ink", "muted")
CSS_VARS = (("ink", "--om-ink"), ("paper", "--om-paper"), ("accent", "--om-accent"),
            ("accent_ink", "--om-accent-ink"), ("muted", "--om-muted"))
SIMPLE_SELECTOR = re.compile(r"(\.[A-Za-z][\w-]*|[a-z][a-z0-9]*)")


# ---------------------------------------------------------------- the page


class _Ids(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: set = set()

    def handle_starttag(self, tag, attrs):
        for k, v in attrs:
            if k == "id" and v:
                self.ids.add(v)


def html_ids(html: str) -> set:
    """Every element id in the page."""
    p = _Ids()
    p.feed(html)
    return p.ids


VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class _Count(HTMLParser):
    """Counts the elements matching a simple selector (`.class` or a tag) inside the element with an id."""

    def __init__(self, el_id: str, selector: str) -> None:
        super().__init__(convert_charrefs=True)
        self.el_id, self.selector = el_id, selector
        self.depth, self.inside, self.count = 0, 0, 0

    def _match(self, tag, attrs) -> bool:
        if self.selector.startswith("."):
            classes = (dict(attrs).get("class") or "").split()
            return self.selector[1:] in classes
        return tag == self.selector

    def handle_starttag(self, tag, attrs):
        if self.inside and self._match(tag, attrs):
            self.count += 1
        if tag in VOID:
            return
        self.depth += 1
        if not self.inside and dict(attrs).get("id") == self.el_id:
            self.inside = self.depth

    def handle_startendtag(self, tag, attrs):
        if self.inside and self._match(tag, attrs):
            self.count += 1

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if self.inside and self.depth == self.inside:
            self.inside = 0
        self.depth -= 1


def count_items(html: str, el_id: str, selector: str) -> int:
    """How many elements inside #el_id match `selector` (a `.class` or a tag name)."""
    p = _Count(el_id, selector)
    p.feed(html)
    return p.count


def with_counts(doc: dict, html: str) -> dict:
    """The doc with each `pop` cue that has `each` given `params.count` (its items in the page), which the
    sound placement and motion.js's events read."""
    out = json.loads(json.dumps(doc))
    for c in out.get("cues", []):
        each = (c.get("params") or {}).get("each")
        if c.get("part") == "pop" and each:
            c["params"]["count"] = count_items(html, c["id"], each)
    return out


# ---------------------------------------------------------------- cues.json


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def validate_cues(doc, ids) -> list:
    """Every problem with a cues doc against the page's element ids, all at once; empty when it can play."""
    if not isinstance(doc, dict):
        return ["cues.json must be a JSON object"]
    problems = []
    if doc.get("version") != VERSION:
        problems.append(f"version must be {VERSION}, got {doc.get('version')!r}")
    fps = doc.get("fps", 30)
    if not isinstance(fps, int) or isinstance(fps, bool) or fps <= 0:
        problems.append(f"fps must be a whole number over 0, got {fps!r}")
    size = doc.get("size", [1080, 1920])
    if not (isinstance(size, list) and len(size) == 2 and all(isinstance(n, int) and n > 0 for n in size)):
        problems.append(f"size must be [width, height] in pixels, got {size!r}")
    duration = doc.get("duration")
    if not _num(duration) or duration <= 0:
        problems.append(f"duration must be seconds over 0, got {duration!r}")
    if "words" in doc and not isinstance(doc["words"], str):
        problems.append("words must be the path of a words.json file")
    cues = doc.get("cues")
    if not isinstance(cues, list):
        return problems + ["cues must be a list"]
    for k, c in enumerate(cues):
        if not isinstance(c, dict):
            problems.append(f"cues[{k}] must be an object")
            continue
        where = f"cues[{k}] ({c.get('id', '?')})"
        if not isinstance(c.get("id"), str) or not c.get("id"):
            problems.append(f"cues[{k}]: needs an id (an element id in index.html)")
        elif c["id"] not in ids:
            problems.append(f"{where}: no element with id {c['id']!r} in index.html")
        out_id = (c.get("params") or {}).get("out") if isinstance(c.get("params"), dict) else None
        if c.get("part") == "scene" and out_id is not None and (out_id not in ids or out_id == c.get("id")):
            problems.append(f"{where}: params.out must name the outgoing scene (another element in index.html), got {out_id!r}")
        if c.get("part") not in PARTS:
            problems.append(f"{where}: unknown part {c.get('part')!r} (one of {', '.join(PARTS)})")
        at = c.get("at")
        if isinstance(at, dict):
            problems += _word_at_problems(where, at)
            if "snap" in c:
                problems.append(f"{where}: a cue at a word keeps its word's time, so it cannot also snap to the beat")
        elif not _num(at) or at < 0:
            problems.append(f"{where}: at must be seconds (0 or more) or {{line, word}}, got {at!r}")
        if "dur" in c and (not _num(c["dur"]) or c["dur"] <= 0):
            problems.append(f"{where}: dur must be seconds over 0, got {c['dur']!r}")
        if "params" in c and not isinstance(c["params"], dict):
            problems.append(f"{where}: params must be an object")
        if "snap" in c and c["snap"] not in SNAPS:
            problems.append(f"{where}: snap must be beat or bar, got {c['snap']!r}")
        if "sfx" in c:
            if not isinstance(c["sfx"], list):
                problems.append(f"{where}: sfx must be a list of sound names")
            else:
                for name in c["sfx"]:
                    if name not in SFX:
                        problems.append(f"{where}: unknown sfx {name!r} (one of {', '.join(SFX)})")
        problems += _param_problems(where, c)
    return problems


# Params the runtime and the sound placement do arithmetic with (from / to are objects for move, numbers for
# odometer: checked per part below).
NUMBER_PARAMS = ("gap", "pad", "draw", "stagger", "tilt", "wave_speed", "lift", "from_scale", "rotate",
                 "rotate_from", "damping", "freq", "from_blur", "cone_x", "cone_w", "typing", "dur", "stretch", "blur")
COUNT_PARAMS = ("max_words", "max_chars", "rows", "cols")


def _param_problems(where: str, c: dict) -> list:
    p = c.get("params") if isinstance(c.get("params"), dict) else {}
    part, out = c.get("part"), []
    for key in NUMBER_PARAMS:
        if key in p and not _num(p[key]):
            out.append(f"{where}: params.{key} must be a number, got {p[key]!r}")
    for key in COUNT_PARAMS:
        if key in p and not (_num(p[key]) and p[key] >= 1 and float(p[key]).is_integer()):
            out.append(f"{where}: params.{key} must be a whole number, 1 or more, got {p[key]!r}")
    if "flip_at" in p and p["flip_at"] is not None and not (_num(p["flip_at"]) and p["flip_at"] >= 0):
        out.append(f"{where}: params.flip_at must be seconds or null, got {p['flip_at']!r}")
    if part == "scene":
        if p.get("kind", "slide") not in SCENE_KINDS:
            out.append(f"{where}: params.kind must be one of {', '.join(SCENE_KINDS)}, got {p.get('kind')!r}")
        if p.get("from", "right") not in SCENE_FROM:
            out.append(f"{where}: params.from must be one of {', '.join(SCENE_FROM)}, got {p.get('from')!r}")
    if part == "odometer" and "from" in p and not _num(p["from"]):
        out.append(f"{where}: params.from must be a number, got {p['from']!r}")
    if part == "odometer" and not _num(p.get("to")):
        out.append(f"{where}: an odometer needs params.to (a number)")
    if part == "move":
        if "ease" in p and p["ease"] not in EASES:
            out.append(f"{where}: unknown ease {p['ease']!r} (one of {', '.join(EASES)})")
        for side in ("from", "to"):
            if side in p and not isinstance(p[side], dict):
                out.append(f"{where}: params.{side} must be an object of x, y, scale, rotate, opacity, blur")
    if part == "pop" and p.get("each") and not SIMPLE_SELECTOR.fullmatch(str(p["each"])):
        out.append(f"{where}: params.each must be a .class or a tag name, got {p['each']!r}")
    if part == "chart" and not (isinstance(p.get("values"), list) and p["values"] and all(_num(v) for v in p["values"])):
        out.append(f"{where}: a chart needs params.values (a list of numbers)")
    if part == "morph":
        states = p.get("states")
        if not isinstance(states, list) or len(states) < 2:
            out.append(f"{where}: a morph needs params.states (two or more shapes)")
        else:
            ats = [s.get("at") if isinstance(s, dict) else None for s in states]
            if not all(_num(a) for a in ats) or ats != sorted(ats):
                out.append(f"{where}: each morph state needs an at, in time order")
    return out


def _word_at_problems(where: str, at: dict) -> list:
    out = [f"{where}: at has unknown key {k!r} (line, word, offset)" for k in at if k not in ("line", "word", "offset")]
    if not isinstance(at.get("line"), str) or not at["line"]:
        out.append(f"{where}: at.line must be a line id from lines.json")
    if not (isinstance(at.get("word"), int) and not isinstance(at.get("word"), bool) and at["word"] >= 1):
        out.append(f"{where}: at.word must be a word number, 1 for the line's first word, got {at.get('word')!r}")
    if "offset" in at and not _num(at["offset"]):
        out.append(f"{where}: at.offset must be seconds, got {at['offset']!r}")
    return out


def word_timed(cue) -> bool:
    """Whether a cue starts at a word of the voice (`at: {line, word, offset?}`)."""
    return isinstance(cue, dict) and isinstance(cue.get("at"), dict)


def resolve_word_times(cues: list, words: list) -> tuple:
    """(cues, problems): each cue whose at is {line, word, offset?} given the start of that word of that line
    (word 1 is the line's first) plus offset, in seconds. The words are words.json from kit.py voice, each tagged
    with its line."""
    by_line = {}
    for w in words:
        if isinstance(w, dict) and w.get("line") is not None:
            by_line.setdefault(w["line"], []).append(w)
    out, problems = [dict(c) if word_timed(c) else c for c in cues], []
    for c in out:
        if not word_timed(c):
            continue
        at, where = c["at"], f"{c['id']}: at {c['at']}"
        line = by_line.get(at["line"])
        if not by_line:
            problems.append(f"{where}: the words file has no line ids; make it with kit.py voice")
        elif line is None:
            problems.append(f"{where}: no line {at['line']!r} in the words (lines: {', '.join(map(str, by_line))})")
        elif at["word"] > len(line):
            problems.append(f"{where}: line {at['line']!r} has {len(line)} words")
        else:
            c["at"] = round(max(0.0, line[at["word"] - 1]["start"] + float(at.get("offset", 0))), 3)
    return out, problems


def cues_js(doc: dict) -> str:
    """The page's data file: `window.ONCA_CUES = {...};`."""
    return "window.ONCA_CUES = " + json.dumps(doc, ensure_ascii=True, separators=(",", ":")) + ";\n"


# ---------------------------------------------------------------- brand.json


def validate_brand(doc) -> list:
    if not isinstance(doc, dict):
        return ["brand.json must be a JSON object"]
    problems = []
    for key in doc:
        if key not in BRAND_DEFAULTS:
            problems.append(f"brand.json: unknown token {key!r} (one of {', '.join(BRAND_DEFAULTS)})")
    for key in COLOURS:
        if key in doc and not (isinstance(doc[key], str) and HEX.fullmatch(doc[key])):
            problems.append(f"brand.json: {key} must be a colour like #D99A0E, got {doc[key]!r}")
    for key in FONT_TOKENS:
        if key in doc and not (isinstance(doc[key], str) and doc[key].strip() and '"' not in doc[key]):
            problems.append(f"brand.json: {key} must be a font name, got {doc[key]!r}")
    files = doc.get("font_files", {})
    if not isinstance(files, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in files.items()):
        problems.append("brand.json: font_files must map a font name to a file in the project")
    return problems


def _font_stack(name: str, fallback: str) -> str:
    return f'"{name}", {fallback}'


def brand_css(brand: dict) -> str:
    """The brand's CSS variables (and a @font-face per font file), defaults where a token is unset; an unset
    muted is mixed from ink and paper, so it always sits between them."""
    b = dict(BRAND_DEFAULTS, **brand)
    lines = []
    for name, path in sorted((b.get("font_files") or {}).items()):
        lines.append(f'@font-face {{ font-family: "{name}"; src: url("{Path(path).as_posix()}"); font-display: block; }}')
    lines.append(":root {")
    for key, var in CSS_VARS:
        value = b[key] if key != "muted" or "muted" in brand else "color-mix(in oklch, var(--om-ink) 60%, var(--om-paper))"
        lines.append(f"  {var}: {value};")
    for key, var, fallback in FONT_VARS:
        lines.append(f"  {var}: {_font_stack(b[key], fallback)};")
    lines.append("}")
    return "\n".join(lines) + "\n"


def _luminance(hex_colour: str) -> float:
    rgb = [int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(a: str, b: str) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


# Role tests, the same as the dashboard's brand preview (pickPalette): a name only suggests a role, the colour
# has to pass the role's test.
MIN_ACCENT_CHROMA = 24  # below this RGB chroma a colour is a grey
PAPER_MIN_LUMINANCE = 0.8
DARK_PAPER_MAX_LUMINANCE = 0.05
MIN_INK_RATIO = 4.5
MIN_ACCENT_RATIO = 3
WHITE, DEFAULT_INK = "#FFFFFF", "#1C1B18"


def _chroma(hex_colour: str) -> int:
    rgb = [int(hex_colour[i:i + 2], 16) for i in (1, 3, 5)]
    return max(rgb) - min(rgb)


def _named(colours: list, pattern: str) -> list:
    return [c for c in colours if re.search(pattern, c["name"], re.I)]


def pick_palette(colors, fixed=None) -> dict:
    """paper, ink, accent and accent_ink picked by role from a brand kit's colors (the dashboard's pickPalette),
    each tested against the paper actually used (`fixed` holds the roles the brand already set), plus muted only
    from a grey named for it. Only roles a kit colour fills; empty when the kit has no valid colour."""
    fixed = fixed or {}
    valid = [{"name": str(c.get("name", "")), "hex": str(c["hex"]).strip().upper()} for c in (colors or [])
             if isinstance(c, dict) and HEX.fullmatch(str(c.get("hex", "")).strip())]
    if not valid:
        return {}
    out = {}
    by_sat = sorted((c for c in valid if _chroma(c["hex"]) >= MIN_ACCENT_CHROMA), key=lambda c: -_chroma(c["hex"]))
    named_accents = _named(valid, r"primary|brand|main|accent")
    first = (named_accents or by_sat or [None])[0]
    rest = [c for c in valid if c is not first] if len(valid) > 1 else valid
    if "paper" in fixed:
        paper = fixed["paper"]
    else:
        light = sorted((c for c in rest if _luminance(c["hex"]) >= PAPER_MIN_LUMINANCE), key=lambda c: -_luminance(c["hex"]))
        dark_ground = [c for c in _named(rest, r"background|paper") if _luminance(c["hex"]) <= DARK_PAPER_MAX_LUMINANCE]
        paper_colour = (_named(light, r"background|paper") or dark_ground or _named(light, r"light|white") or light or [None])[0]
        paper = paper_colour["hex"] if paper_colour else BRAND_DEFAULTS["paper"]
        if paper_colour:
            out["paper"] = paper

    def reads(c):
        return (_chroma(c["hex"]) >= MIN_ACCENT_CHROMA and c["hex"] != paper
                and _contrast(c["hex"], paper) >= MIN_ACCENT_RATIO)
    accent_colour = next((c for c in named_accents + by_sat if reads(c)), first if first and first["hex"] != paper else None)
    if accent_colour:
        out["accent"] = accent_colour["hex"]
    others = [c for c in valid if c is not accent_colour] if len(valid) > 1 else valid
    readable = [c for c in others if _contrast(c["hex"], paper) >= MIN_INK_RATIO]
    named_ink = sorted(_named(readable, r"text|ink|dark|black"), key=lambda c: -_contrast(c["hex"], paper))
    if named_ink or readable:
        out["ink"] = (named_ink or [min(readable, key=lambda c: _luminance(c["hex"]))])[0]["hex"]
    if "accent" in out:
        ink = fixed.get("ink", out.get("ink", DEFAULT_INK))
        out["accent_ink"] = max((WHITE, ink, DEFAULT_INK), key=lambda c: _contrast(c, out["accent"]))
    muted = [c for c in _named(valid, r"muted|secondary|grey|gray") if _chroma(c["hex"]) < MIN_ACCENT_CHROMA]
    if muted:
        out["muted"] = muted[0]["hex"]
    return out


def brand_from_kit(kit: dict, brand: dict) -> dict:
    """The brand with every token the client left unset filled from a get_brand_kit answer (colours by role test
    against the brand's own paper, pick_palette; fonts by use). Tokens already set never change; a token the kit
    does not give stays unset (brand.css uses the default), so a later run can still fill it from a richer kit."""
    out = dict(brand)
    for role, value in pick_palette(kit.get("colors"), brand).items():
        if role == "accent_ink" and "accent" in brand:
            continue  # worked out below from the brand's own accent
        out.setdefault(role, value)
    fonts = [f for f in (kit.get("fonts") or []) if isinstance(f, dict) and str(f.get("name", "")).strip()]
    for f in fonts:
        use = str(f.get("use", "")).lower()
        if any(w in use for w in ("display", "heading", "title", "headline")) and "display_font" not in out:
            out["display_font"] = f["name"].strip()
        elif any(w in use for w in ("body", "text", "ui", "copy")) and "body_font" not in out:
            out["body_font"] = f["name"].strip()
    if fonts:
        out.setdefault("display_font", fonts[0]["name"].strip())
        out.setdefault("body_font", fonts[-1]["name"].strip())
    if "accent_ink" not in out and "accent" in out:
        accent, ink, paper = (out.get(k, BRAND_DEFAULTS[k]) for k in ("accent", "ink", "paper"))
        out["accent_ink"] = ink if _contrast(accent, ink) >= _contrast(accent, paper) else paper
    return out


# ---------------------------------------------------------------- brand fonts

BUNDLED_FONTS = ("DM Serif Display", "Caveat")  # declared in motion.css, files in kit/fonts/
FONT_SUFFIXES = (".woff2", ".ttf", ".otf", ".woff")
_STYLE_WORDS = re.compile(r"(variablefont|font|static|pt|regular|normal|book|roman|text|display|variable|vf|webfont|latin|italic|ital|opsz|wdth|"
                          r"wght|slnt|thin|hairline|extralight|ultralight|light|medium|semibold|demibold|bold|"
                          r"extrabold|ultrabold|black|heavy|\d)*")


def _font_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def font_match(family: str, filename: str) -> bool:
    """Whether a font file belongs to the family: its name is the family plus style words only
    (BricolageGrotesque[opsz,wdth,wght].ttf and Geist-Regular.woff2 match; GeistMono-Regular.woff2 is not Geist)."""
    path = Path(filename)
    key, stem = _font_key(family), _font_key(re.sub(r"\[[^\]]*\]", "", path.stem))  # [opsz,wght] axes
    return bool(key) and path.suffix.lower() in FONT_SUFFIXES and stem.startswith(key) and bool(
        _STYLE_WORDS.fullmatch(stem[len(key):]))


def pick_font_file(family: str, names: list):
    """The best file of the family among `names` (a variable font, else the regular, else any), or None."""
    hits = [n for n in names if font_match(family, n)]

    def rank(n):
        stem = _font_key(re.sub(r"\[[^\]]*\]", "", Path(n).stem))[len(_font_key(family)):]
        variable = "[" in n or "variable" in stem or "wght" in stem
        return ("italic" in stem, not variable, stem not in ("", "regular"),
                FONT_SUFFIXES.index(Path(n).suffix.lower()), n)
    return min(hits, key=rank) if hits else None


def font_dirs(platform: str, home, env: dict) -> list:
    """The system's font folders, user first."""
    home = Path(home)
    fam = _family(platform)
    if fam == "darwin":
        return [home / "Library" / "Fonts", Path("/Library/Fonts"), Path("/System/Library/Fonts"),
                Path("/System/Library/Fonts/Supplemental")]
    if fam == "win32":
        return [Path(env[k]) / sub for k, sub in (("LOCALAPPDATA", "Microsoft/Windows/Fonts"), ("WINDIR", "Fonts"))
                if env.get(k)]
    return [home / ".local" / "share" / "fonts", home / ".fonts", Path("/usr/local/share/fonts"), Path("/usr/share/fonts")]


def brand_fonts(brand: dict, kit_fonts=()) -> list:
    """The font families the video names that need a file: the brand's display, body and label fonts and the
    kit's fonts, less the bundled ones and those that already have a file."""
    have = set(brand.get("font_files") or {})
    names = [*(brand.get(k) for k in FONT_TOKENS), *kit_fonts]
    out = []
    for n in names:
        if isinstance(n, str) and n.strip() and n not in BUNDLED_FONTS and n not in have and n not in out:
            out.append(n.strip())
    return out


def google_fonts_link(family: str) -> str:
    """Where the client can find a Google font's files (the CSS lists each file's link)."""
    return "https://fonts.googleapis.com/css2?family=" + family.strip().replace(" ", "+")


# ---------------------------------------------------------------- beats and voice


def snap(cues: list, beats: dict, max_shift: float = 0.15) -> tuple:
    """(cues, notes): each cue with `snap` moved onto the nearest beat (`beat`) or bar (`bar`) when it is at
    most max_shift away; nothing moves when the beat confidence is under 0.5."""
    out = json.loads(json.dumps(cues))
    notes = []
    if not any("snap" in c for c in out):
        return out, notes
    conf = beats.get("bpmConfidence") or 0
    if conf < BEAT_CONFIDENCE:
        notes.append(f"beats: confidence {conf:g} is under {BEAT_CONFIDENCE:g}, nothing snapped")
        return out, notes
    for c in out:
        kind = c.get("snap")
        if kind not in SNAPS:
            continue
        grid = beats.get("beatTimes" if kind == "beat" else "bars") or []
        if not grid:
            notes.append(f"{c['id']}: no {kind} times, kept at {c['at']:g}")
            continue
        near = min(grid, key=lambda b: abs(b - c["at"]))
        if abs(near - c["at"]) <= max_shift + 1e-9:
            if near != c["at"]:
                notes.append(f"{c['id']}: {c['at']:g} -> {near:g} ({kind})")
            c["at"] = round(near, 3)
        else:
            notes.append(f"{c['id']}: the nearest {kind} is {abs(near - c['at']):.2f} s away, kept at {c['at']:g}")
    return out, notes


def bars(beat_times: list) -> list:
    """Every 4th beat, from the first."""
    return list(beat_times[::4])


SENTENCE_END = re.compile(r"[.!?\u2026][\"'\u201d\u2019)\]]*$")


def _runs(words: list) -> list:
    """The words cut wherever a voice line ends or a sentence ends (also behind a closing quote or bracket)."""
    out = []
    for w in words:
        if not out or w.get("line") != out[-1][-1].get("line") or SENTENCE_END.search(out[-1][-1]["text"]):
            out.append([])
        out[-1].append(w)
    return out


def chunks(words: list, max_words: int, max_chars: int = 24) -> list:
    """Caption chunks: never across a voice line's or a sentence's end, and inside one grouped as video-edit's
    captions are (a chunk ends at a clause's end or a pause, a short comma phrase joins the next, a long phrase
    is cut into even pieces of at most max_words and max_chars)."""
    if max_words < 1:
        raise ValueError("max_words must be 1 or more")
    return [g["words"] for run in _runs(words) for g in edit_core.caption_groups(run, max_words, max_chars)]


def _rel(w: dict, at: float) -> dict:
    return {"text": w["text"], "start": round(w["start"] - at, 3), "end": round(w["end"] - at, 3)}


def voiced(cue) -> bool:
    """Whether a cue takes its words from the voice: a `words` cue with from_voice, a `captions` cue unless
    from_voice is false."""
    if not isinstance(cue, dict) or cue.get("part") not in ("words", "captions"):
        return False
    p = cue.get("params") or {}
    return isinstance(p, dict) and bool(p.get("from_voice", cue["part"] == "captions"))


def voice_words(cues: list, words: list) -> list:
    """Each cue with `params.from_voice` given the voice's words inside its window ([at, at + dur), or from at
    on without a dur), times in seconds from the cue's at: `words` cues get params.words, `captions` cues get
    params.chunks (at most max_words each)."""
    out = json.loads(json.dumps(cues))
    for c in out:
        if not voiced(c):
            continue
        p = c.setdefault("params", {})
        at, end = c["at"], c["at"] + c["dur"] if "dur" in c else math.inf
        inside = [w for w in words if at - 1e-9 <= w["start"] < end]
        if c["part"] == "words":
            p["words"] = [_rel(w, at) for w in inside]
        else:
            p["chunks"] = [[_rel(w, at) for w in ch]
                           for ch in chunks(inside, int(p.get("max_words", 4)), int(p.get("max_chars", 24)))]
    return out


# ---------------------------------------------------------------- voice lines


def _item_problems(items: list, label: str, keys: tuple) -> list:
    """Each item an object with every key a non-empty string, and no id used twice."""
    problems, seen = [], set()
    for k, item in enumerate(items):
        if not isinstance(item, dict):
            problems.append(f"{label}[{k}] must be an object")
            continue
        for key in keys:
            if not isinstance(item.get(key), str) or not item[key].strip():
                problems.append(f"{label}[{k}]: needs {key}")
        if item.get("id") in seen:
            problems.append(f"{label}[{k}]: id {item.get('id')!r} is used twice")
        seen.add(item.get("id"))
    return problems


LINE_ID = re.compile(r"[A-Za-z0-9_-]+")


def validate_lines(doc) -> list:
    """Every problem with a lines.json: {lead?, gap?, lines: [{id, file, text, at?}]}."""
    if not isinstance(doc, dict) or not isinstance(doc.get("lines"), list) or not doc["lines"]:
        return ["lines.json must be an object with a non-empty lines list"]
    problems = []
    for key in ("lead", "gap"):
        if key in doc and not (_num(doc[key]) and doc[key] >= 0):
            problems.append(f"{key} must be seconds, 0 or more, got {doc[key]!r}")
    problems += _item_problems(doc["lines"], "lines", ("id", "file", "text"))
    problems += [f"lines[{k}]: id {ln['id']!r} may hold only letters, digits, _ and - (it names voice-lines/ID.wav)"
                 for k, ln in enumerate(doc["lines"]) if isinstance(ln, dict) and isinstance(ln.get("id"), str)
                 and ln["id"].strip() and not LINE_ID.fullmatch(ln["id"])]
    for k, ln in enumerate(doc["lines"]):
        if isinstance(ln, dict) and "at" in ln and not (_num(ln["at"]) and ln["at"] >= 0):
            problems.append(f"lines[{k}]: at must be seconds, 0 or more, got {ln['at']!r}")
    return problems


def place_lines(lines: list, durations: dict, lead: float = 0.3, gap: float = 0.25) -> list:
    """Each line at its own `at`, else `gap` after the line before (the first at `lead`):
    [{id, file, text, at, end}]. ValueError when a line would start before the one ahead of it ends."""
    out, t, end = [], lead, 0.0
    for ln in lines:
        at = float(ln.get("at", t))
        if at < end - 1e-6:
            raise ValueError(f"line {ln['id']} starts at {at:g} s, before the line ahead of it ends at {end:g} s")
        end = at + float(durations[ln["id"]])
        out.append({"id": ln["id"], "file": ln["file"], "text": ln["text"].strip(), "at": round(at, 3), "end": round(end, 3)})
        t = end + gap
    return out


def _spread(words: list, start: float, end: float) -> list:
    """Words spread over [start, end] by length."""
    total = sum(len(w) + 1 for w in words) or 1
    out, t = [], start
    for w in words:
        d = (end - start) * (len(w) + 1) / total
        out.append({"text": w, "start": round(t, 3), "end": round(t + d, 3)})
        t += d
    return out


def _norm(word: str) -> str:
    return re.sub(r"[^\w]", "", word.lower())


def script_words(placed: list, asr=None) -> list:
    """The narration's words as the script spells them, [{text, start, end, line}] in seconds from the video's
    start, each tagged with its line's id: times from the recognised words when given (matched by difflib, a
    misheard word takes the time of the word heard in its place), else spread over each line by length."""
    return [dict(w, line=ln["id"]) for ln in placed for w in _line_words(ln, asr)]


def _line_words(ln: dict, asr) -> list:
    """One placed line's words, timed from the recognised words inside it, else spread."""
    import difflib
    words = ln["text"].split()
    heard = [w for w in (asr or []) if ln["at"] - 0.05 <= w["start"] < ln["end"] + 0.05]
    if not heard:
        return _spread(words, ln["at"], ln["end"])
    times = [None] * len(words)
    ops = difflib.SequenceMatcher(None, [_norm(w) for w in words], [_norm(w["text"]) for w in heard], autojunk=False)
    for op, i1, i2, j1, j2 in ops.get_opcodes():
        if op == "equal" or (op == "replace" and i2 - i1 == j2 - j1):
            for k in range(i2 - i1):
                times[i1 + k] = (heard[j1 + k]["start"], heard[j1 + k]["end"])
        elif op == "replace":
            for k, w in enumerate(_spread(words[i1:i2], heard[j1]["start"], heard[j2 - 1]["end"])):
                times[i1 + k] = (w["start"], w["end"])
    out, k = [], 0
    while k < len(words):
        if times[k] is not None:
            out.append({"text": words[k], "start": round(times[k][0], 3), "end": round(times[k][1], 3)})
            k += 1
            continue
        j = k
        while j < len(words) and times[j] is None:
            j += 1
        start = times[k - 1][1] if k > 0 else ln["at"]
        end = times[j][0] if j < len(words) else ln["end"]
        out += _spread(words[k:j], start, max(start, end))
        k = j
    return out


# Tightening a voice line: generated speech carries silence at its ends and long pauses between words.
MAX_PAUSE = 0.28
TEMPO_RANGE = (0.9, 1.15)  # a gentle tempo change; past it the voice sounds processed


def keep_spans(levels: list, floor: float, max_pause=MAX_PAUSE, pad: float = 0.06, hop: float = edit_core.LEVEL_HOP) -> list:
    """[(start, end)] seconds of a line to keep, from its level per `hop` (video-edit's levels_db) and the level
    under which a frame is quiet (its quiet_floor): the quiet before the first sound and after the last trimmed
    to `pad`, and each pause inside longer than `max_pause` cut to `max_pause` (half kept on each side, so words
    keep their tail and their attack; None keeps every pause). [] for a line with no sound."""
    loud = [level >= floor for level in levels]
    if not any(loud):
        return []
    first, last = loud.index(True), len(loud) - 1 - loud[::-1].index(True)
    spans, start, k = [], max(0.0, first * hop - pad), first
    while k <= last:
        if loud[k]:
            k += 1
            continue
        j = k
        while not loud[j]:  # stops by `last`, which is loud
            j += 1
        if max_pause is not None and (j - k) * hop > max_pause:
            spans.append((start, k * hop + max_pause / 2))
            start = j * hop - max_pause / 2
        k = j
    spans.append((start, min(len(levels) * hop, (last + 1) * hop + pad)))
    return [(round(a, 3), round(b, 3)) for a, b in spans]


def fade_edges(samples, rate: int, seconds: float = 0.008) -> None:
    """A short linear fade in and out at the ends of one kept piece of 16-bit samples, in place, so a cut never
    clicks."""
    n = min(int(rate * seconds), len(samples) // 2)
    for k in range(n):
        samples[k] = int(samples[k] * k / n)
        samples[-1 - k] = int(samples[-1 - k] * k / n)


def voice_mix_args(placed: list, seconds: float, out, tempo: float = 1.0) -> list:
    """ffmpeg's arguments after the binary: every line placed at its time (sped up by `tempo`, pitch kept) in one
    48 kHz mono 16-bit WAV of `seconds`."""
    args = ["-v", "error", "-y"]
    for ln in placed:
        args += ["-i", str(ln["file"])]
    speed = f"atempo={tempo:g}," if tempo != 1 else ""
    chains = [f"[{k}:a]aresample=48000,aformat=channel_layouts=mono,{speed}adelay={int(round(ln['at'] * 1000))}:all=1[a{k}]"
              for k, ln in enumerate(placed)]
    mix = "".join(f"[a{k}]" for k in range(len(placed)))
    chains.append(f"{mix}amix=inputs={len(placed)}:normalize=0:dropout_transition=0,apad,atrim=0:{seconds:.3f}[v]")
    return args + ["-filter_complex", ";".join(chains), "-map", "[v]", "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", str(out)]


# ---------------------------------------------------------------- the engine's check, read for the kit

# The kit mixes the sound after the render (kit.py sound), so a render's own check always finds no sound.
EXPECTED_FINDINGS = ("film_silent", "audio_none", "audio_file_without_element")


def check_summary(report: dict) -> dict:
    """The engine's `check --json` report as {errors, warnings, expected}: one line per finding, the findings
    the kit's own route explains moved to `expected`."""
    out = {"errors": [], "warnings": [], "expected": []}
    for section, body in (report or {}).items():
        if not isinstance(body, dict) or not isinstance(body.get("findings"), list):
            continue
        for f in body["findings"]:
            if not isinstance(f, dict) or f.get("severity") not in ("error", "warning"):
                continue
            where = " ".join(str(x) for x in (f.get("selector"), f"at {f['time']:g} s" if _num(f.get("time")) else None) if x)
            line = f"{section}: {f.get('code')}: {f.get('message', '')}" + (f" ({where})" if where else "")
            if f.get("code") in EXPECTED_FINDINGS:
                out["expected"].append(line)
            else:
                out["errors" if f["severity"] == "error" else "warnings"].append(line)
    return out


# ---------------------------------------------------------------- the local picker page


def validate_choices(doc) -> list:
    """Every problem with a choices.json: {title?, choices: [{id, name, file}]}."""
    if not isinstance(doc, dict) or not isinstance(doc.get("choices"), list) or not doc["choices"]:
        return ["choices.json must be an object with a non-empty choices list"]
    return _item_problems(doc["choices"], "choices", ("id", "name", "file"))


PICKER_CSS = (
    "body{font:16px/1.4 system-ui,sans-serif;margin:0 auto;max-width:720px;padding:24px 16px;background:#F6F1E7;"
    "color:#151412}h1{font-size:22px;margin:0 0 4px}.hint{margin:0 0 16px;color:#5E594F;font-size:14px}"
    "ul{list-style:none;margin:0;padding:0;display:grid;gap:10px;grid-template-columns:repeat(auto-fill,minmax(150px,1fr))}"
    "li{position:relative;display:flex}button{font:inherit;cursor:pointer}button:focus-visible{outline:3px solid #2F6FEB;"
    "outline-offset:2px}.card{width:100%;min-height:64px;padding:12px 52px 12px 14px;text-align:left;font-weight:600;"
    "border:2px solid #D9D2C3;border-radius:12px;background:#fff;color:#151412;overflow-wrap:anywhere}"
    ".card:hover:not(:disabled){border-color:#151412}.card[aria-pressed=true]{background:#151412;color:#fff;"
    "border-color:#151412}.card[aria-pressed=true]::before{content:'\\2713  '}"
    ".play{position:absolute;right:10px;top:50%;transform:translateY(-50%);width:34px;height:34px;padding:0;"
    "border-radius:50%;border:0;background:#151412;color:#fff;display:grid;place-items:center}"
    ".play:hover:not(:disabled){background:#3A3832}.play svg{width:14px;height:14px;fill:currentColor}"
    ".play .i-pause,.play[aria-pressed=true] .i-play{display:none}.play[aria-pressed=true] .i-pause{display:block}"
    "li:has(.card[aria-pressed=true]) .play{background:#fff;color:#151412}"
    "button:disabled{cursor:default}.picked .card:not([aria-pressed=true]){opacity:.45}"
    ".picked .play:disabled{opacity:.45}#done{font-weight:600;min-height:1.4em}")
PICKER_JS = (
    "const players={};"
    "function mark(k,on){const b=document.getElementById('p'+k);b.setAttribute('aria-pressed',String(on));"
    "b.setAttribute('aria-label',(on?'Pause ':'Play ')+b.dataset.name);}"
    "function play(k){let a=players[k];if(!a){a=players[k]=new Audio('/audio/'+k);a.onplay=()=>mark(k,true);"
    "a.onpause=a.onended=()=>mark(k,false);}if(!a.paused){a.pause();return;}"
    "Object.values(players).forEach(o=>o.pause());a.play().catch(()=>mark(k,false));}"
    "function pick(k){Object.values(players).forEach(o=>o.pause());"
    "document.querySelectorAll('button').forEach(b=>b.disabled=true);"
    "document.getElementById('c'+k).setAttribute('aria-pressed','true');document.body.classList.add('picked');"
    "const done=document.getElementById('done');fetch('/pick/'+k,{method:'POST'}).then(r=>r.text())"
    ".then(t=>{done.textContent=t;}).catch(()=>{done.textContent='Could not save the pick. Tell your AI client.';});}")
PLAY_ICONS = ('<svg class="i-play" viewBox="0 0 14 14" aria-hidden="true"><path d="M3 1.5v11l9.5-5.5z"/></svg>'
              '<svg class="i-pause" viewBox="0 0 14 14" aria-hidden="true"><path d="M2.5 1.5h3v11h-3zM8.5 1.5h3v11h-3z"/></svg>')


def byte_range(header, size: int):
    """(start, end) of a `Range: bytes=a-b` request inside `size` bytes, or None for the whole file."""
    m = re.fullmatch(r"bytes=(\d*)-(\d*)", str(header or "").strip())
    if not m or not size or (not m.group(1) and not m.group(2)):
        return None
    if not m.group(1):  # the last N bytes
        return max(0, size - int(m.group(2))), size - 1
    start = int(m.group(1))
    end = min(int(m.group(2)), size - 1) if m.group(2) else size - 1
    return (start, end) if start <= end else None


def picker_html(title: str, choices: list) -> str:
    """The picker page: a grid of cards, each one button with only the choice's name that picks it, and a small round
    play / pause button beside the name that plays its sample (one at a time) and never picks."""
    import html as _h
    rows = "".join(
        f'<li><button id="c{k}" class="card" type="button" aria-pressed="false" onclick="pick({k})">'
        f'{_h.escape(c["name"])}</button><button id="p{k}" class="play" type="button" aria-pressed="false" '
        f'data-name="{_h.escape(c["name"])}" aria-label="Play {_h.escape(c["name"])}" onclick="play({k})">'
        f'{PLAY_ICONS}</button></li>' for k, c in enumerate(choices))
    return (f"<!doctype html><html lang='en'><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
            f"<title>{_h.escape(title)}</title><style>{PICKER_CSS}</style><main><h1>{_h.escape(title)}</h1>"
            f"<p class='hint'>Press play to listen. Click a name to pick it.</p><ul>{rows}</ul>"
            f"<p id='done' role='status' aria-live='polite'></p></main><script>{PICKER_JS}</script></html>")


# ---------------------------------------------------------------- platform plan

REMBG_PIN = "2.0.87"
REMBG_MODEL = "isnet-general-use"  # Apache 2.0; rembg's default model (BRIA RMBG) is non-commercial
NODE_MAJOR = 22
CUTOUT_SWIFT = Path(__file__).resolve().parent / "cutout.swift"
INSTALL = {
    "darwin": {"node": "brew install node@22", "ffmpeg": "brew install ffmpeg", "uv": "brew install uv",
               "swift": "xcode-select --install", "chrome": "brew install --cask google-chrome"},
    "win32": {"node": "winget install OpenJS.NodeJS.LTS", "ffmpeg": "winget install Gyan.FFmpeg",
              "uv": "winget install --id=astral-sh.uv -e", "chrome": "winget install Google.Chrome"},
    "linux": {"node": "install Node 22 or newer from https://nodejs.org/en/download",
              "ffmpeg": "install ffmpeg from https://ffmpeg.org/download.html",
              "uv": "install uv from https://docs.astral.sh/uv/getting-started/installation/",
              "chrome": "install Google Chrome from https://www.google.com/chrome/"},
}


def _family(platform: str) -> str:
    if platform == "darwin":
        return "darwin"
    if platform.startswith("win"):
        return "win32"
    return "linux"


def platform_plan(platform: str, macos_major=None, swift: bool = False) -> dict:
    """How this machine runs the kit's tools: the render engine route, the cut-out engine and the install line
    of each tool. The only place the kit decides by platform."""
    fam = _family(platform)
    vision = fam == "darwin" and macos_major is not None and macos_major >= 14 and swift
    return {"engine": "npx" if fam == "win32" else "sh", "cutout": "vision" if vision else "rembg",
            "install": dict(INSTALL[fam])}


def chrome_candidates(platform: str, env: dict) -> list:
    """Where Chrome lives on this platform (paths first, then names to find on PATH)."""
    fam = _family(platform)
    if fam == "darwin":
        return ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Chromium.app/Contents/MacOS/Chromium", "google-chrome", "chromium"]
    if fam == "win32":
        roots = [env[k] for k in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA") if env.get(k)]
        return [str(Path(r) / "Google" / "Chrome" / "Application" / "chrome.exe") for r in roots] + ["chrome"]
    return ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"]


def shot_command(chrome, page_url: str, out, width: int, height: int, scale: float, profile) -> list:
    """Headless Chrome's own screenshot of a page at a device scale, on a transparent ground."""
    return [str(chrome), "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
            "--no-default-browser-check", f"--user-data-dir={profile}", f"--window-size={width},{height}",
            f"--force-device-scale-factor={scale:g}", "--default-background-color=00000000", f"--screenshot={out}",
            page_url]


def node_ok(version_text: str) -> bool:
    """True for Node 22 or newer (`node --version` prints v22.4.0)."""
    m = re.search(r"v?(\d+)\.", str(version_text or ""))
    return bool(m) and int(m.group(1)) >= NODE_MAJOR


def engine_command(platform: str, engine_script, pin: str, npx) -> list:
    """The render engine's command line: video-render's `sh engine` where there is a sh, else npx with the pin."""
    if platform_plan(platform)["engine"] == "npx":
        return [str(npx), "--yes", f"hyperframes@{pin}"]
    return ["sh", str(engine_script)]


def cutout_command(engine: str, src, out, swift, uv) -> list:
    """The cut-out command: Apple Vision through cutout.swift, or rembg with its commercial-safe model (always
    with -m) in a uv-managed Python 3.12."""
    if engine == "vision":
        return [str(swift), str(CUTOUT_SWIFT), str(src), str(out)]
    if engine == "rembg":
        return [str(uv), "run", "--python", "3.12", "--with", f"rembg[cpu,cli]=={REMBG_PIN}", "rembg", "i",
                "-m", REMBG_MODEL, str(src), str(out)]
    raise ValueError(f"unknown cut-out engine {engine!r}")


def rembg_line() -> str:
    return " ".join(cutout_command("rembg", "IN.png", "OUT.png", "uv", "uv"))


# ---------------------------------------------------------------- PNG (8-bit RGB / RGBA, not interlaced)


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else (b if pb <= pc else c)


def png_size(data: bytes) -> tuple:
    """(width, height) from a PNG's header, without decoding it."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    return struct.unpack(">II", data[16:24])


def read_png(data: bytes) -> tuple:
    """(width, height, rows): rows of RGBA bytes. ValueError for anything but 8-bit RGB or RGBA."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    i, idat, w = 8, b"", 0
    while i < len(data):
        n, kind = struct.unpack(">I4s", data[i:i + 8])
        body = data[i + 8:i + 8 + n]
        if kind == b"IHDR":
            w, h, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", body)
            if depth != 8 or ctype not in (2, 6) or interlace:
                raise ValueError("only 8-bit RGB or RGBA PNGs without interlace")
        elif kind == b"IDAT":
            idat += body
        i += 12 + n
    bpp = 4 if ctype == 6 else 3
    raw, stride, rows, prev = zlib.decompress(idat), w * bpp, [], bytearray(w * bpp)
    for y in range(h):
        f, line = raw[y * (stride + 1)], bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for x in range(stride):
            a = line[x - bpp] if x >= bpp else 0
            b, c = prev[x], prev[x - bpp] if x >= bpp else 0
            line[x] = (line[x] + (0, a, b, (a + b) // 2, _paeth(a, b, c))[f]) & 0xFF
        prev = line
        if bpp == 3:
            rgba = bytearray()
            for x in range(w):
                rgba += line[x * 3:x * 3 + 3] + b"\xff"
            line = rgba
        rows.append(bytes(line))
    return w, h, rows


def write_png(w: int, h: int, rows: list) -> bytes:
    """An RGBA PNG from rows of RGBA bytes."""
    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + bytes(r) for r in rows)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def trim(w: int, h: int, rows: list, pad: int = 8) -> tuple:
    """(w, h, rows) cropped to the opaque pixels plus `pad`; unchanged when nothing is opaque."""
    xs, ys = [], []
    for y, r in enumerate(rows):
        hit = [x for x in range(w) if r[x * 4 + 3] > 8]
        if hit:
            ys.append(y)
            xs += (hit[0], hit[-1])
    if not ys:
        return w, h, rows
    x0, x1 = max(0, min(xs) - pad), min(w - 1, max(xs) + pad)
    y0, y1 = max(0, ys[0] - pad), min(h - 1, ys[-1] + pad)
    return x1 - x0 + 1, y1 - y0 + 1, [r[x0 * 4:(x1 + 1) * 4] for r in rows[y0:y1 + 1]]
