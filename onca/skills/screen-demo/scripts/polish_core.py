"""The pure half of polish.py: from a click log to zoom segments, camera keyframes, cursor keyframes and the
stage layout. Positions are CSS pixels of the source viewport, times seconds from its start.

Written from the published descriptions of the auto-zoom and cursor look of screen-recording tools (zoom in
before a click, hold, ease out; smoothed, enlarged cursor); no code is taken from any of them.
"""

from __future__ import annotations

import math

PRESS_KINDS = ("click", "tap", "key")
POINTER_KINDS = ("move", "click", "tap")


def _r(v: float) -> float:
    return round(v, 3)


def clusters(events: list[dict], merge_gap: float = 1.6) -> list[list[dict]]:
    """Click, tap and key events grouped while each is within `merge_gap` s of the one before."""
    presses = sorted((e for e in events if e["kind"] in PRESS_KINDS), key=lambda e: e["t"])
    out: list[list[dict]] = []
    for e in presses:
        if out and e["t"] - out[-1][-1]["t"] <= merge_gap:
            out[-1].append(e)
        else:
            out.append([e])
    return out


def zoom_plan(log: dict, scale: float = 1.8, lead: float = 0.45, ramp: float = 0.6, hold: float = 1.0,
              merge_gap: float = 1.6) -> list[dict]:
    """One zoom segment per cluster: ramp in to `full` (`lead` s before the first press), hold to `until`
    (`hold` s after the last), ramp out to `end`; clamped to the log and overlapping segments merged."""
    duration = log["duration"]

    def clamp(v):
        return _r(min(duration, max(0.0, v)))

    plan: list[dict] = []
    for group in clusters(log["events"], merge_gap):
        full = group[0]["t"] - lead
        until = group[-1]["t"] + hold
        seg = {"start": clamp(full - ramp), "full": clamp(full), "until": clamp(until), "end": clamp(until + ramp),
               "scale": scale, "points": [{"t": e["t"], "x": e["x"], "y": e["y"]} for e in group]}
        if plan and seg["start"] <= plan[-1]["end"]:
            prev = plan[-1]
            prev.update(until=seg["until"], end=seg["end"])
            prev["points"] += seg["points"]
        else:
            plan.append(seg)
    return plan


def view_center(x: float, y: float, scale: float, w: float, h: float) -> tuple[float, float]:
    """The center of a `scale`-times view on (x, y), moved so the view stays inside the w x h source."""
    hw, hh = w / scale / 2, h / scale / 2
    return _r(min(max(x, hw), w - hw)), _r(min(max(y, hh), h - hh))


def _framed_center(x: float, y: float, scale: float, w: float, h: float, view: tuple[float, float]) -> tuple[float, float]:
    """Like view_center, for an output frame that shows `view` source pixels at scale 1: the frame stays filled by
    the recording where it is smaller than it, and centered where it is larger."""
    vw, vh = view[0] / scale, view[1] / scale
    cx = min(max(x, vw / 2), w - vw / 2) if vw < w else w / 2
    cy = min(max(y, vh / 2), h - vh / 2) if vh < h else h / 2
    return _r(cx), _r(cy)


def camera_keys(plan: list[dict], w: float, h: float, duration: float, base: float = 1.0,
                view: tuple[float, float] | None = None) -> list[dict]:
    """Camera keyframes {t, scale, cx, cy}, strictly ascending from 0 to `duration`. Between segments the
    camera rests at `base` on the last place it looked at (the middle at first); `base` > 1 keeps a 9:16 crop
    filled and following the action. `view` (the output frame in source pixels at scale 1) clamps to what the
    frame really shows instead of the w x h view."""
    keys: list[dict] = []

    def add(t, scale, x, y):
        cx, cy = _framed_center(x, y, scale, w, h, view) if view else view_center(x, y, scale, w, h)
        key = {"t": _r(t), "scale": scale, "cx": cx, "cy": cy}
        if keys and key["t"] <= keys[-1]["t"]:
            keys[-1] = key
        else:
            keys.append(key)

    last = (w / 2, h / 2)
    add(0, base, *last)
    for seg in plan:
        s = max(seg["scale"], base)
        pts = seg["points"]
        add(seg["start"], base, *last)
        add(seg["full"], s, pts[0]["x"], pts[0]["y"])
        for p in pts:
            if seg["full"] < p["t"] < seg["until"]:
                add(p["t"], s, p["x"], p["y"])
        add(seg["until"], s, pts[-1]["x"], pts[-1]["y"])
        last = (pts[-1]["x"], pts[-1]["y"])
        add(seg["end"], base, *last)
    if keys[-1]["t"] < duration:
        add(duration, base, *last)
    return keys


def _cubic(p: float) -> float:
    return 4 * p * p * p if p < 0.5 else 1 - (-2 * p + 2) ** 3 / 2


def camera_at(keys: list[dict], t: float) -> dict:
    """The camera at time t, exactly as the polish page computes it (cubic ease between keys)."""
    if t <= keys[0]["t"]:
        return {k: keys[0][k] for k in ("scale", "cx", "cy")}
    for a, b in zip(keys, keys[1:]):
        if t < b["t"]:
            p = _cubic(min(1.0, max(0.0, (t - a["t"]) / (b["t"] - a["t"]))))
            return {k: a[k] + (b[k] - a[k]) * p for k in ("scale", "cx", "cy")}
    return {k: keys[-1][k] for k in ("scale", "cx", "cy")}


def cursor_keys(log: dict, glide_max: float = 0.7, glide_min: float = 0.25, min_gap: float = 0.15,
                jitter: float = 4.0, start: tuple[float, float] | None = None) -> list[dict]:
    """Cursor keyframes {t, from, x, y, click}: the cursor rests at the previous key until `from`, then glides
    to this key by `t`. Every click or tap is kept at its exact time and place; a move is kept only when it is
    at least `min_gap` s after and `jitter` px away from the last kept key."""
    keys: list[dict] = []
    if start is not None:
        keys.append({"t": 0.0, "from": 0.0, "x": start[0], "y": start[1], "click": False, "hand": False})
    for e in sorted((e for e in log["events"] if e["kind"] in POINTER_KINDS), key=lambda e: e["t"]):
        press = e["kind"] != "move"
        if not press and keys:
            last = keys[-1]
            if e["t"] - last["t"] < min_gap or math.hypot(e["x"] - last["x"], e["y"] - last["y"]) < jitter:
                continue
        if keys and press and e["t"] == keys[-1]["t"]:
            keys.pop()
        keys.append({"t": _r(e["t"]), "from": _r(e["t"]), "x": e["x"], "y": e["y"], "click": press, "hand": bool(e.get("hand"))})
    for prev, k in zip(keys, keys[1:]):
        glide = min(glide_max, max(glide_min, k["t"] - prev["t"]))
        k["from"] = _r(max(prev["t"], k["t"] - glide))
    return keys


def stage_layout(out_w: int, out_h: int, src_w: int, src_h: int, pad: float = 0.06) -> dict:
    """The recording's box on the output frame: fitted inside a padding of `pad` x the shorter side, centered."""
    margin = pad * min(out_w, out_h)
    scale = min((out_w - 2 * margin) / src_w, (out_h - 2 * margin) / src_h)
    w, h = src_w * scale, src_h * scale
    return {"x": round((out_w - w) / 2, 2), "y": round((out_h - h) / 2, 2), "w": round(w, 2), "h": round(h, 2),
            "radius": 18, "scale": round(scale, 6)}
