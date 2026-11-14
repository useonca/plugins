"""Sound effects on motion: the hits a cues doc causes (the same list motion.js's events gives), their placement
on the takes of the sound pack, and the video-edit timeline that mixes them. Pure."""

from __future__ import annotations

import math
from pathlib import Path

import kit_core

SFX = kit_core.SFX
# Each effect's level under the final loudness pass (the mix is brought to -16 LUFS as a whole).
GAIN_DB = {"whoosh": -6, "whoosh-short": -8, "pop": -4, "tick": -10, "key": -10, "typing": -8, "sent": -4,
           "received": -4, "notification": -4, "tap": -6, "riser": -6, "impact": -4}
MIN_GAP = 0.12
WHOOSH_MAX_DUR = 0.45
WHOOSH_MIN_DIST = 300


def _r(t: float) -> float:
    return round(t + 0.0, 3)


def _default_hits(c: dict) -> list:
    """(t from the cue's at, sfx name) for each moment the part itself sounds."""
    part, p = c["part"], c.get("params") or {}
    dur = c.get("dur", kit_core.DUR.get(part))
    if part == "highlight":
        return [(p.get("draw", 0.35), "pop")]
    if part == "odometer":
        return [(0, "tick"), (dur, "tick")]
    if part == "pop":
        stagger = p.get("stagger", 0.06)
        return [(i * stagger, "pop") for i in range(int(p.get("count", 1)) if p.get("each") else 1)]
    if part == "drop":
        return [(dur, "tap")]
    if part == "move":
        a, b = p.get("from") or {}, p.get("to") or {}
        dist = math.hypot(b.get("x", 0) - a.get("x", 0), b.get("y", 0) - a.get("y", 0))
        return [(0, "whoosh")] if dur <= WHOOSH_MAX_DUR + 1e-9 and dist >= WHOOSH_MIN_DIST else []
    if part == "chart":
        return [(p.get("draw", 1.0), "pop")]
    if part == "spotlight":
        return [] if p.get("flip_at") is None else [(p["flip_at"], "whoosh")]
    if part == "bubble":
        return [(p.get("typing", 0.9), "sent" if p.get("side", "in") == "out" else "received")]
    if part == "morph":
        return [(s["at"], "whoosh-short") for s in (p.get("states") or [])[1:]]
    if part == "scene":
        return {"cut": [], "whip": [(0, "whoosh")]}.get(p.get("kind", "slide"), [(0, "whoosh-short")])
    return []


def hits(doc: dict) -> list:
    """[{t, cue, sfx}] sorted by time: each part's own hits, renamed by the cue's `sfx` list (hit k takes
    sfx[k % len]); `sfx: []` silences a cue; a part with no hits of its own sounds once at its at when given
    an sfx list."""
    out = []
    for c in doc.get("cues", []):
        own = _default_hits(c)
        names = c.get("sfx")
        if names is not None:
            if not names:
                own = []
            elif not own:
                own = [(0, names[0])]
            else:
                own = [(t, names[k % len(names)]) for k, (t, _) in enumerate(own)]
        out += [{"t": _r(c["at"] + t), "cue": c["id"], "sfx": name} for t, name in own]
    out.sort(key=lambda h: h["t"])  # stable: cue order, then hit order, breaks ties
    return out


def place(hits_list: list, index: dict, fps: int, min_gap: float = MIN_GAP) -> list:
    """[{src, in, out, at, gain_db}]: of two hits closer than min_gap the earlier keeps its effect; each name's
    takes rotate in time order over the kept hits; each take starts so its peak lands one frame after the hit."""
    placed, last, turn = [], None, {}
    frame = 1.0 / fps
    for h in sorted(hits_list, key=lambda x: x["t"]):
        if last is not None and h["t"] - last < min_gap - 1e-9:
            continue
        takes = index.get(h["sfx"])
        if not takes:
            raise ValueError(f"the sound pack has no {h['sfx']!r}")
        last = h["t"]
        take = takes[turn.get(h["sfx"], 0) % len(takes)]
        turn[h["sfx"]] = turn.get(h["sfx"], 0) + 1
        at = h["t"] + frame - take["peak"]
        cut = max(0.0, -at)
        placed.append({"src": take["file"], "in": round(cut, 4), "out": round(take["dur"], 4), "at": round(max(0.0, at), 4),
                       "gain_db": GAIN_DB.get(h["sfx"], -6)})
    return placed


def _key(path: str) -> str:
    return "sfx-" + Path(path).stem


def timeline(doc: dict, video: str, placed: list, music=None, voice=None, music_db: float = -18) -> dict:
    """A video-edit timeline: the silent render as the main track, its sound from `voice` (a narration or a
    silence WAV), the effects, and the music bed under it all, loudness -16."""
    duration = float(doc["duration"])
    w, h = doc.get("size", [1080, 1920])
    sources = {"main": str(video), "voice": str(voice)}
    audio = []
    for p in placed:
        sources[_key(p["src"])] = str(p["src"])
        audio.append({"src": _key(p["src"]), "in": p["in"], "out": p["out"], "at": p["at"], "gain_db": p["gain_db"]})
    tl = {"version": 1, "fps": doc.get("fps", 30), "sources": sources, "audio_from": {"main": "voice"},
          "main": [{"src": "main", "in": 0, "out": duration}], "audio": audio,
          "outputs": [{"name": "with-sound", "size": f"{w}x{h}"}], "loudness": -16}
    if music:
        sources["bed"] = str(music)
        tl["music"] = [{"src": "bed", "in": 0, "at": 0, "dur": duration, "gain_db": music_db, "fade_in": 0.5,
                        "fade_out": 1.5, "duck_db": 10}]
    return tl


def peak_offset(samples, rate: int) -> float:
    """Seconds from the start to the largest absolute sample."""
    if not samples:
        raise ValueError("no samples")
    best = max(range(len(samples)), key=lambda i: abs(samples[i]))
    return best / float(rate)
