"""Pure decisions for the timeline: one JSON edit compiled to one ffmpeg render per output.

A timeline has a main track (clips of the talk, butt-joined), overlays on top (a cutaway, the speaker as
picture-in-picture, a logo), extra audio and music, captions, and the output sizes. Every clip is its own
input seeked to its start, so footage the edit does not use is never decoded. Layouts are fractions of the
output frame, so one timeline serves every size. The sound is rendered once (mix.wav) and muxed into each output.
"""

from __future__ import annotations

import re

import compose
import core

VERSION = 1
ENCODERS = {
    # Higher -q:v is better for VideoToolbox. speed.py on an M4: q55 VMAF 89, q62 92, q70 94 (x264 medium 95), so q70.
    "videotoolbox": ["-c:v", "h264_videotoolbox", "-q:v", "70", "-profile:v", "high", "-pix_fmt", "yuv420p"],
    "x264": ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-profile:v", "high", "-pix_fmt", "yuv420p"],
    "x264-fast": ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-profile:v", "high", "-pix_fmt", "yuv420p"],
}
NEEDS = {"videotoolbox": "h264_videotoolbox", "x264": "libx264", "x264-fast": "libx264"}
LAYOUTS = ("full", "pip", "box")
CORNERS = ("tl", "tr", "bl", "br")
FITS = ("cover", "contain")
MAX_ZOOM = 1.5
ZOOM_AT = [0.5, 0.35]  # where a punch-in centres: faces sit above the middle
SAFE_BAND = (285 / 1920, 1440 / 1920)  # a tall video's caption band stays in this part of the height
MIN_ZOOM_GAP = 4.0  # seconds between two zoom changes
SENTENCE_END = ".!?"
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp")
EDGE_FADE = 0.025  # every speech piece fades in and out this long, so a cut never clicks
PIP_MARGIN = 0.04  # of the shorter side
EPS = 1e-3


def num(x: float) -> str:
    """A time for a filter: up to 4 decimals, no trailing zeros (5.0 -> "5")."""
    return ("%.4f" % float(x)).rstrip("0").rstrip(".") or "0"


def is_image(path: str) -> bool:
    return str(path).lower().endswith(IMAGE_EXT)


# ---------------------------------------------------------------- encoders


def pick_encoder(name: str, available: set) -> str:
    """`auto`: VideoToolbox when this ffmpeg has it, else libx264 veryfast. ValueError for an unknown name
    or one this ffmpeg cannot run."""
    if name == "auto":
        return "videotoolbox" if NEEDS["videotoolbox"] in available else "x264-fast"
    if name not in ENCODERS:
        raise ValueError(f"unknown encoder {name}: use auto, {', '.join(ENCODERS)}")
    if NEEDS[name] not in available:
        raise ValueError(f"encoder {name} needs {NEEDS[name]}, which this ffmpeg does not list")
    return name


# ---------------------------------------------------------------- validate


def clip_dur(c: dict) -> float:
    return float(c["dur"]) if "dur" in c else float(c["out"]) - float(c["in"])


def main_length(tl: dict) -> float:
    return round(sum(float(c["out"]) - float(c["in"]) for c in tl["main"]), 4)


def _size(text) -> tuple:
    m = re.fullmatch(r"(\d+)x(\d+)", str(text or ""))
    return (int(m.group(1)), int(m.group(2))) if m else None


def _check_range(where: str, c: dict, durations: dict, src: str, problems: list) -> None:
    try:
        a, b = float(c["in"]), float(c["out"])
    except (KeyError, TypeError, ValueError):
        problems.append(f"{where}: needs numbers `in` and `out`")
        return
    if b <= a:
        problems.append(f"{where}: out {b} is not after in {a}")
    if a < 0:
        problems.append(f"{where}: in {a} is before the start")
    end = durations.get(src)
    if end is not None and b > end + EPS:
        problems.append(f"{where}: out {b} is past the end of {src} ({end} s)")


def validate(tl: dict, durations: dict) -> list:
    """Every problem with a timeline, all at once; empty when it can render. `durations` maps each source
    key to its length in seconds (None for a still image)."""
    if not isinstance(tl, dict):
        return ["a timeline is a JSON object"]
    problems = []
    if tl.get("version") != VERSION:
        problems.append(f"version must be {VERSION}, got {tl.get('version')!r}")
    sources = tl.get("sources") or {}
    if not isinstance(sources, dict) or not sources:
        problems.append("sources: a map of name -> file is required")
        sources = {}

    def known(where, src):
        if src not in sources:
            problems.append(f"{where}: unknown source {src!r} (not in sources)")
            return False
        return True

    main = tl.get("main") or []
    if not main:
        problems.append("main: at least one clip is required")
    for k, c in enumerate(main):
        where = f"main[{k}]"
        if known(where, c.get("src")):
            _check_range(where, c, durations, c["src"], problems)
        _check_zoom(where, c, problems)
    length = main_length({"main": [c for c in main if _num_ok(c, "in") and _num_ok(c, "out")]})

    for k, o in enumerate(tl.get("overlays") or []):
        where = f"overlays[{k}]"
        src = o.get("src")
        if src == "@main":
            if "in" in o or "out" in o:
                problems.append(f"{where}: @main takes `at` and `dur` only")
        elif known(where, src):
            if is_image(sources[src]) or "dur" in o:
                if not _num_ok(o, "dur") or float(o["dur"]) <= 0:
                    problems.append(f"{where}: needs a positive `dur`")
            else:
                _check_range(where, o, durations, src, problems)
        try:
            at, d = float(o.get("at", -1)), clip_dur(o)
        except (KeyError, TypeError, ValueError):
            problems.append(f"{where}: needs `at` and a length (`in`/`out` or `dur`)")
            continue
        if at < 0:
            problems.append(f"{where}: needs `at` (seconds on the output)")
        elif at + d > length + EPS:
            problems.append(f"{where}: {num(at)}-{num(at + d)} s runs past the main track's end ({num(length)} s)")
        _check_layout(where, o, problems)
        per = o.get("per_output") or {}
        names = {out.get("name") for out in tl.get("outputs") or []}
        for name in per if isinstance(per, dict) else []:
            if name not in names:
                problems.append(f"{where}: per_output names {name!r}, which is not an output")
            elif not per[name].get("hide"):
                _check_layout(f"{where} in {name}", dict(o, **per[name]), problems)

    for k, c in enumerate(tl.get("audio") or []):
        where = f"audio[{k}]"
        if known(where, c.get("src")):
            _check_range(where, c, durations, c["src"], problems)
        if not _num_ok(c, "at") or float(c["at"]) < 0:
            problems.append(f"{where}: needs `at` (seconds on the output)")
    for k, m in enumerate(tl.get("music") or []):
        where = f"music[{k}]"
        known(where, m.get("src"))
        if not _num_ok(m, "dur") or float(m["dur"]) <= 0:
            problems.append(f"{where}: needs a positive `dur`")
    for a, b in (tl.get("audio_from") or {}).items():
        known(f"audio_from[{a}]", a)
        known(f"audio_from[{a}]", b)
    for src in ((tl.get("captions") or {}).get("words") or {}):
        known(f"captions.words[{src}]", src)

    outputs = tl.get("outputs") or []
    if not outputs:
        problems.append("outputs: at least one output is required")
    names = [o.get("name") for o in outputs]
    for name in sorted({n for n in names if names.count(n) > 1}, key=str):
        problems.append(f"outputs: the name {name!r} is used twice")
    for k, o in enumerate(outputs):
        if not o.get("name"):
            problems.append(f"outputs[{k}]: needs a name")
        if not _size(o.get("size")):
            problems.append(f"outputs[{k}]: size must look like 1080x1920, got {o.get('size')!r}")
        elif tl.get("captions") and band_problem(o):
            problems.append(f"outputs[{k}]: {band_problem(o)}")
    return problems


def _num_ok(d: dict, key: str) -> bool:
    try:
        float(d[key])
        return True
    except (KeyError, TypeError, ValueError):
        return False


def _check_zoom(where: str, c: dict, problems: list) -> None:
    if not 1 <= float(c.get("zoom", 1)) <= MAX_ZOOM:
        problems.append(f"{where}: zoom must be between 1 and {MAX_ZOOM:g}, got {c.get('zoom')!r}")
    at = c.get("zoom_at", ZOOM_AT)
    if not (isinstance(at, list) and len(at) == 2 and all(isinstance(v, (int, float)) and 0 <= v <= 1 for v in at)):
        problems.append(f"{where}: zoom_at must be [x, y] fractions of the frame, got {at!r}")


def _check_layout(where: str, o: dict, problems: list) -> None:
    layout = o.get("layout", "full")
    if layout not in LAYOUTS:
        problems.append(f"{where}: layout {layout!r} is not one of {', '.join(LAYOUTS)}")
        return
    if o.get("fit", "cover") not in FITS:
        problems.append(f"{where}: fit {o.get('fit')!r} is not cover or contain")
    if float(o.get("fade", 0) or 0) < 0:
        problems.append(f"{where}: fade cannot be negative")
    if layout == "pip":
        if o.get("corner", "br") not in CORNERS:
            problems.append(f"{where}: corner {o.get('corner')!r} is not one of {', '.join(CORNERS)}")
        if not 0 < float(o.get("scale", 0.28)) <= 1:
            problems.append(f"{where}: scale must be between 0 and 1")
    if layout == "box":
        box = o.get("box")
        ok = isinstance(box, list) and len(box) == 4 and all(isinstance(v, (int, float)) for v in box)
        if not ok or min(box) < 0 or box[2] <= 0 or box[3] <= 0 or box[0] + box[2] > 1 + EPS or box[1] + box[3] > 1 + EPS:
            problems.append(f"{where}: box must be [x, y, w, h] fractions inside the frame, got {box!r}")


# ---------------------------------------------------------------- the main track on the output timeline


def snap_main(tl: dict) -> dict:
    """The timeline with each main clip's `in` and `out` on its frame grid: a clip's picture is a whole number of
    frames, so its sound must be too, or picture and sound drift apart over the cuts."""
    fps = float(tl.get("fps", 30) or 30)
    main = [dict(c, **{k: core.snap(float(c[k]), fps) for k in ("in", "out") if _num_ok(c, k)}) for c in tl.get("main") or []]
    return dict(tl, main=main)


def main_spans(tl: dict) -> list:
    """(output start, output end, clip) for each main clip."""
    out, t = [], 0.0
    for c in tl["main"]:
        d = float(c["out"]) - float(c["in"])
        out.append((round(t, 4), round(t + d, 4), c))
        t += d
    return out


def source_time(tl: dict, t: float) -> tuple:
    """The main source and its time at output time t (a clip boundary belongs to the next clip)."""
    spans = main_spans(tl)
    for a, b, c in spans:
        if a - EPS <= t < b - EPS or (c is spans[-1][2] and abs(t - b) <= EPS):
            return c["src"], round(float(c["in"]) + t - a, 4)
    raise ValueError(f"{t} s is outside the main track (0-{main_length(tl)} s)")


def _main_pieces(tl: dict, at: float, dur: float) -> list:
    """The main clips seen at output [at, at + dur]: (output start, output end, src, source time)."""
    out = []
    for a, b, c in main_spans(tl):
        s, e = max(a, at), min(b, at + dur)
        if e - s > EPS:
            out.append((round(s, 4), round(e, 4), c["src"], round(float(c["in"]) + s - a, 4)))
    return out


def ends_sentence(text: str) -> bool:
    """A word that ends a sentence: its last mark, past closing quotes and brackets, is . ! or ?"""
    t = text.rstrip("\"')]}\u201d\u2019")
    return bool(t) and t[-1] in SENTENCE_END


def zoom_problems(tl: dict, words: list, min_gap: float = MIN_ZOOM_GAP) -> list:
    """Zoom changes that jump while someone talks: a change between two main clips is fine
    on a cut (the source jumps, a new shot anyway), or right before a sentence starts and at least `min_gap`
    after the last change.
    `words` are on the output clock (`words_out`). [{"at", "why"}]."""
    out, last = [], None
    spans = main_spans(tl)
    for (_a0, _b0, p), (a, _b, c) in zip(spans, spans[1:]):
        if (float(p.get("zoom", 1)), p.get("zoom_at", ZOOM_AT)) == (float(c.get("zoom", 1)), c.get("zoom_at", ZOOM_AT)):
            continue
        cut = p["src"] != c["src"] or abs(float(p["out"]) - float(c["in"])) > EPS
        if not cut:
            nxt = next((k for k, w in enumerate(words) if w["start"] >= a - EPS), None)
            inside = any(w["start"] < a - EPS < w["end"] for w in words)
            starts = nxt is not None and words[nxt]["start"] - a <= 0.6 and (nxt == 0 or ends_sentence(words[nxt - 1]["text"]))
            if inside or not starts:
                out.append({"at": round(a, 3), "why": "the zoom jumps mid-sentence (change it on a cut or where a sentence starts)"})
        if not cut and last is not None and a - last < min_gap:
            out.append({"at": round(a, 3), "why": f"the zoom changes {a - last:.1f} s after the last change (at least {min_gap:g} s)"})
        last = a
    return out


def words_out(tl: dict, words_by_src: dict) -> list:
    """Kept words of the main clips on the output timeline, caption rewrites (`captions.retext`) applied."""
    out = []
    for a, _b, c in main_spans(tl):
        cin, cout = float(c["in"]), float(c["out"])
        for w in words_by_src.get(c["src"], []):
            mid = (w["start"] + w["end"]) / 2
            if cin <= mid <= cout:
                s = max(w["start"], cin) - cin + a
                e = min(w["end"], cout) - cin + a
                out.append({"i": w["i"], "text": w["text"], "start": round(s, 3), "end": round(e, 3)})
    return core.tidy_text(out, (tl.get("captions") or {}).get("retext"))


def from_edl(edl: dict, outputs: list) -> dict:
    """The timeline of today's cut: one main clip per kept range, no overlays, no substitutes."""
    return {"version": VERSION, "fps": edl["fps"], "sources": {"main": edl["source"]}, "audio_from": {},
            "main": [{"src": "main", "in": r["start"], "out": r["end"]} for r in edl["ranges"]],
            "overlays": [], "audio": [], "music": [], "outputs": outputs, "loudness": -16}


# ---------------------------------------------------------------- compile: sound


def _seek(src: str, start: float, dur: float) -> list:
    return ["-ss", num(start), "-t", num(dur), "-i", src]


def _audio_in(label: str, extra: str, out: str) -> str:
    return f"[{label}]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo{extra}[{out}]"


def speech_runs(main: list) -> list:
    """The main clips with each run that carries straight on (same source, out == next in) as one clip: a
    split for a zoom is no cut in the sound."""
    out = []
    for c in main:
        if out and out[-1]["src"] == c["src"] and abs(float(out[-1]["out"]) - float(c["in"])) <= EPS:
            out[-1] = dict(out[-1], out=c["out"])
        else:
            out.append(dict(c))
    return out


def audio_graph(tl: dict, durations: dict) -> dict:
    """The one sound render: speech (main clips, or their `audio_from` substitute) with every edge faded,
    extra audio clips placed at their time, music ducked under the speech. Output label [mix]."""
    sources, subst = tl["sources"], tl.get("audio_from") or {}
    inputs, parts, k = [], [], 0
    speech = []
    for j, c in enumerate(speech_runs(tl["main"])):
        d = float(c["out"]) - float(c["in"])
        inputs.append(_seek(sources[subst.get(c["src"], c["src"])], float(c["in"]), d))
        f = min(EDGE_FADE, d / 4)
        parts.append(_audio_in(f"{k}:a", f",afade=t=in:st=0:d={num(f)},afade=t=out:st={num(d - f)}:d={num(f)}", f"s{j}"))
        speech.append(f"[s{j}]")
        k += 1
    parts.append("".join(speech) + f"concat=n={len(speech)}:v=0:a=1[speech]")
    extra = []
    for j, c in enumerate(tl.get("audio") or []):
        inputs.append(_seek(sources[c["src"]], float(c["in"]), float(c["out"]) - float(c["in"])))
        ms = int(round(float(c["at"]) * 1000))
        parts.append(_audio_in(f"{k}:a", f",volume={num(c.get('gain_db', 0))}dB,adelay={ms}:all=1", f"ac{j}"))
        extra.append(f"[ac{j}]")
        k += 1
    music = tl.get("music") or []
    if music:
        parts.append(f"[speech]asplit={len(music) + 1}[sp]" + "".join(f"[key{j}]" for j in range(len(music))))
    for j, m in enumerate(music):
        d = float(m["dur"])
        inputs.append(["-stream_loop", "-1"] + _seek(sources[m["src"]], float(m.get("in", 0)), d))
        fi, fo = float(m.get("fade_in", 0)), float(m.get("fade_out", 0))
        fades = (f",afade=t=in:st=0:d={num(fi)}" if fi > 0 else "") + (f",afade=t=out:st={num(d - fo)}:d={num(fo)}" if fo > 0 else "")
        ms = int(round(float(m.get("at", 0)) * 1000))
        parts.append(_audio_in(f"{k}:a", f",volume={num(m.get('gain_db', -18))}dB{fades},adelay={ms}:all=1", f"m{j}"))
        duck = float(m.get("duck_db", 0))
        if duck > 0:  # speech sits ~16 dB over the key threshold; ratio r takes duck_db off it
            ratio = min(20.0, 16.0 / max(0.5, 16.0 - min(duck, 15.5)))
            parts.append(f"[m{j}][key{j}]sidechaincompress=threshold=0.025:ratio={num(ratio)}:attack=20:release=400[md{j}]")
        else:
            parts.append(f"[key{j}]anullsink;[m{j}]anull[md{j}]")
        extra.append(f"[md{j}]")
        k += 1
    head = "[sp]" if music else "[speech]"
    length = main_length(tl)
    if extra:
        parts.append(f"{head}{''.join(extra)}amix=inputs={1 + len(extra)}:normalize=0:duration=first,atrim=end={num(length)}[mix]")
    else:
        parts.append(f"{head}atrim=end={num(length)}[mix]")
    return {"inputs": inputs, "filter": ";".join(parts), "out": "[mix]"}


def clean_chain(denoise: str = "light") -> str:
    """Voice clean-up before the loudness pass: rumble off, light denoise, gentle compression."""
    if denoise not in ("light", "off"):
        raise ValueError(f"denoise is light or off, not {denoise!r}")
    chain = ["highpass=f=80"]
    if denoise == "light":
        chain.append("afftdn=nr=10:nf=-40")
    chain.append("acompressor=threshold=-18dB:ratio=3:attack=10:release=120:makeup=2")
    return ",".join(chain)


# ---------------------------------------------------------------- compile: picture


def _relabel(chain: str, suffix: str) -> str:
    """Make a filter's own [labels] unique (reframe_filter's fit mode names its branches)."""
    return re.sub(r"\[(\w+)\]", lambda m: f"[{m.group(1)}{suffix}]", chain)


def _even(x: float) -> int:
    return max(2, int(round(x / 2)) * 2)


def punch_in(c: dict, W: int, H: int) -> str:
    """A main clip's `zoom` (a punch-in that makes a jump cut read as a new shot), taken around `zoom_at`
    after the reframe; empty at zoom 1."""
    z = float(c.get("zoom", 1))
    if z <= 1:
        return ""
    w, h = _even(W / z), _even(H / z)
    ax, ay = c.get("zoom_at", ZOOM_AT)
    return f",crop={w}:{h}:{int(round((W - w) * ax))}:{int(round((H - h) * ay))},scale={W}:{H}:flags=lanczos,setsar=1"


def overlay_rect(o: dict, W: int, H: int, src_w: int, src_h: int) -> tuple:
    """Where an overlay lands, in output pixels: (x, y, w, h) of the picture itself."""
    layout = o.get("layout", "full")
    if layout == "pip":
        w = _even(float(o.get("scale", 0.28)) * W)
        h = _even(w * src_h / src_w)
        m = int(round(PIP_MARGIN * min(W, H)))
        corner = o.get("corner", "br")
        x = W - w - m if corner[1] == "r" else m
        y = H - h - m if corner[0] == "b" else m
        return x, y, w, h
    bx, by, bw, bh = (0.0, 0.0, 1.0, 1.0) if layout == "full" else [float(v) for v in o["box"]]
    x, y, w, h = int(round(bx * W)), int(round(by * H)), _even(bw * W), _even(bh * H)
    if o.get("fit", "cover") == "contain":
        scale = min(w / src_w, h / src_h)
        cw, ch = _even(src_w * scale), _even(src_h * scale)
        return x + (w - cw) // 2, y + (h - ch) // 2, cw, ch
    return x, y, w, h


def _scale(o: dict, w: int, h: int) -> str:
    if o.get("layout", "full") != "pip" and o.get("fit", "cover") == "cover":
        return f"scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,crop={w}:{h}"
    return f"scale={w}:{h}:flags=lanczos"


def video_graph(tl: dict, output: dict, probes: dict, captions: dict | None = None) -> dict:
    """The picture of one output: the main track reframed for its size, each overlay at its time, then the
    caption images. Output label [v]. `probes` maps a source key to {"width", "height"}."""
    W, H = _size(output["size"])
    fps = num(tl.get("fps", 30))
    sources = tl["sources"]
    inputs, parts, k = [], [], 0
    labels = []
    for j, c in enumerate(tl["main"]):
        p = probes[c["src"]]
        inputs.append(_seek(sources[c["src"]], float(c["in"]), float(c["out"]) - float(c["in"])))
        vf = core.reframe_filter(p["width"], p["height"], W, H, float(output.get("focus_x", 0.5)), output.get("mode", "auto"))
        parts.append(f"[{k}:v]setpts=PTS-STARTPTS,fps={fps},{_relabel(vf, str(j))}{punch_in(c, W, H)}[mv{j}]")
        labels.append(f"[mv{j}]")
        k += 1
    parts.append("".join(labels) + f"concat=n={len(labels)}:v=1:a=0[base]")
    cur, n = "[base]", 0
    for o in overlays_for(tl, output):
        at, d = float(o["at"]), clip_dur(o)
        if o["src"] == "@main":
            pieces = _main_pieces(tl, at, d)
        else:
            pieces = [(at, at + d, o["src"], float(o.get("in", 0)))]
        for s, e, src, t0 in pieces:
            p = probes[src]
            x, y, w, h = overlay_rect(o, W, H, p["width"], p["height"])
            path = sources[src]
            inputs.append(["-loop", "1", "-t", num(e - s), "-i", path] if is_image(path) else _seek(path, t0, e - s))
            chain = [f"fps={fps}", _scale(o, w, h), "format=yuva420p"]
            fade = min(float(o.get("fade", 0) or 0), (e - s) / 2)
            if fade > 0:
                if abs(s - at) <= EPS:
                    chain.append(f"fade=t=in:st=0:d={num(fade)}:alpha=1")
                if abs(e - (at + d)) <= EPS:
                    chain.append(f"fade=t=out:st={num(e - s - fade)}:d={num(fade)}:alpha=1")
            chain.append(f"setpts=PTS-STARTPTS+{num(s)}/TB")
            parts.append(f"[{k}:v]{','.join(chain)}[ov{n}]")
            parts.append(f"{cur}[ov{n}]overlay=enable='between(t,{num(s)},{num(e)})':x={x}:y={y}:eof_action=pass[b{n}]")
            cur = f"[b{n}]"
            k += 1
            n += 1
    if captions:
        inputs.append(["-f", "concat", "-safe", "0", "-i", captions["list"]])
        parts.append(f"[{k}:v]format=rgba[cap]")
        parts.append(f"{cur}[cap]overlay=x={int(captions['x'])}:y={int(captions['y'])}:eof_action=repeat[capd]")
        cur = "[capd]"
    parts.append(f"{cur}setsar=1,format=yuv420p[v]")
    return {"inputs": inputs, "filter": ";".join(parts), "out": "[v]"}


def render_args(inputs: list, filter: str, maps: list, encoder: list, out: str) -> list:
    """One ffmpeg command line (after `ffmpeg -y`): inputs, the graph, the maps, the encoder, the render contract."""
    args = [a for inp in inputs for a in inp]
    args += ["-filter_complex", filter]
    for m in maps:
        args += ["-map", m]
    args += list(encoder) + ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", out]
    return args


# ---------------------------------------------------------------- captions as images


def output_band(output: dict) -> dict:
    """The caption band for an output: the look's default for its shape and size, with the output's `band`
    (pixels) over it."""
    W, H = _size(output["size"])
    return dict(compose.layout_for(W, H), **(output.get("band") or {}))


def band_problem(output: dict) -> str | None:
    """A tall output's caption band outside y 285-1440 of 1920 (scaled), where the apps' buttons and text sit."""
    W, H = _size(output["size"])
    if H <= W:
        return None
    b = output_band(output)
    top, bottom = SAFE_BAND[0] * H, SAFE_BAND[1] * H
    if b["top"] < top - 0.5 or b["top"] + b["height"] > bottom + 0.5:
        return (f"the caption band (y {b['top']}-{b['top'] + b['height']}) leaves the safe zone y {top:.0f}-{bottom:.0f}, "
                "under the apps' buttons and text")
    return None


def caption_states(groups: list) -> list:
    """One state per lit word: {"start", "end", "group", "lit"}, covering each group from its start to its end."""
    out = []
    for g, group in enumerate(groups):
        words = group["words"]
        for k, w in enumerate(words):
            start = group["start"] if k == 0 else max(group["start"], w["start"])
            end = group["end"] if k == len(words) - 1 else min(group["end"], words[k + 1]["start"])
            if end - start > EPS:
                out.append({"start": round(start, 3), "end": round(end, 3), "group": g, "lit": k})
    return out


def state_key(s: dict) -> str:
    return f"{s['group']}-{s['lit']}"


def caption_concat(states: list, pngs: dict, blank: str, total: float) -> str:
    """The concat demuxer list laying the caption images over 0..total: a blank image wherever no caption
    shows, each state for its time, and the last file again (the demuxer drops the last duration otherwise)."""
    def q(p):
        return "file '" + str(p).replace("'", "'\\''") + "'"

    lines, t, last = ["ffconcat version 1.0"], 0.0, blank
    for s in states:
        if s["start"] - t > EPS:
            lines += [q(blank), f"duration {s['start'] - t:.3f}"]
            t = s["start"]
        last = pngs[state_key(s)]
        lines += [q(last), f"duration {s['end'] - t:.3f}"]
        t = s["end"]
    if total - t > EPS:
        last = blank
        lines += [q(blank), f"duration {total - t:.3f}"]
    lines.append(q(last))
    return "\n".join(lines) + "\n"


def overlays_for(tl: dict, output: dict) -> list:
    """The overlays of one output: each with its `per_output[name]` fields over it, without the hidden ones."""
    out = []
    for o in tl.get("overlays") or []:
        o = dict(o, **(o.get("per_output") or {}).get(output["name"], {}))
        if not o.get("hide"):
            out.append(o)
    return out


def caption_overlaps(tl: dict, output: dict, groups: list, sizes: dict | None = None) -> list:
    """Overlays on screen while captions show over them: a pip or a box under the caption band (the caption
    covers it), and full cutaways (look at those frames: the caption may cover the UI). `sizes` maps a source
    to its (width, height) for a pip's shape (16:9 when missing)."""
    W, H = _size(output["size"])
    band = output_band(output)
    by, bh = band["top"], band["height"]
    sizes = sizes or {}
    main_src = tl["main"][0]["src"] if tl.get("main") else None
    out = []
    for o in overlays_for(tl, output):
        at, d = float(o["at"]), clip_dur(o)
        src = main_src if o["src"] == "@main" else o["src"]
        sw, sh = sizes.get(src, (16, 9))
        x, y, w, h = overlay_rect(o, W, H, sw, sh)
        layout = o.get("layout", "full")
        if layout != "full" and (y >= by + bh or y + h <= by or x >= band["left"] + band["width"] or x + w <= band["left"]):
            continue
        for g in groups:
            s, e = max(at, g["start"]), min(at + d, g["end"])
            if e - s > EPS:
                out.append({"src": o["src"], "kind": layout, "start": round(s, 3), "end": round(e, 3)})
    return out
