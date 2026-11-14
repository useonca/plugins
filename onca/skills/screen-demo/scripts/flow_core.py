"""The pure half of flow.py: a rebuilt screen's flow (flow.json), its step times, and the click log measured
from the page.

A flow plays on a page the client rebuilt from the product's source (rung 1). Each step starts when the one
before it ended plus that step's `pause`; `flow.js` in the page derives every state from the time alone, and
the polish adds the cursor and camera from the click log, as for a recording.
"""

from __future__ import annotations

import re

DEFAULT_PAUSE = 0.8
DEFAULT_CPS = 14
FIRST_STEP = 0.5
TAIL = 1.0
STEP_KEYS = ("show", "click", "tap", "type", "set", "wait", "key")
SET_OPS = ("text", "add", "remove", "attr")


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _css(v) -> bool:
    return isinstance(v, str) and bool(v.strip())


def parse_size(size) -> tuple[int, int] | None:
    m = re.fullmatch(r"(\d+)x(\d+)", size) if isinstance(size, str) else None
    if not m or int(m.group(1)) <= 0 or int(m.group(2)) <= 0:
        return None
    return int(m.group(1)), int(m.group(2))


def _set_problems(where: str, step: dict) -> list[str]:
    out = []
    if not _css(step.get("set")):
        out.append(f"{where}: set needs a CSS selector")
    ops = [k for k in SET_OPS if k in step]
    if len(ops) != 1:
        out.append(f"{where}: set needs exactly one of text, add, remove, attr")
    elif ops[0] == "attr" and not isinstance(step["attr"], dict):
        out.append(f"{where}: attr needs an object of attribute names and values")
    elif ops[0] != "attr" and not isinstance(step[ops[0]], str):
        out.append(f"{where}: {ops[0]} needs text")
    return out


def _action_problems(where: str, action, screens: list[str]) -> list[str]:
    if not isinstance(action, dict) or ("show" in action) == ("set" in action):
        return [f"{where}: then needs one show or set object"]
    if "show" in action:
        return [] if action["show"] in screens else [f"{where}: show id {action['show']!r} is not in screens"]
    return _set_problems(where, action)


def _step_problems(i: int, step, screens: list[str]) -> list[str]:
    where = f"step {i}"
    if not isinstance(step, dict):
        return [f"{where}: must be an object"]
    kinds = [k for k in step if k in STEP_KEYS]
    allowed = set(STEP_KEYS) | {"pause", "then", "into", "cps", "at"} | set(SET_OPS)
    unknown = [k for k in step if k not in allowed]
    if unknown:
        return [f"{where}: unknown step {', '.join(unknown)}"]
    if len(kinds) != 1:
        return [f"{where}: needs exactly one of {', '.join(STEP_KEYS)}"]
    kind = kinds[0]
    out = []
    if kind == "show" and step["show"] not in screens:
        out.append(f"{where}: show id {step['show']!r} is not in screens")
    if kind in ("click", "tap"):
        if not _css(step[kind]):
            out.append(f"{where}: {kind} needs a CSS selector")
        if "then" in step:
            out += _action_problems(where, step["then"], screens)
    if kind == "type":
        if not isinstance(step["type"], str):
            out.append(f"{where}: type needs text")
        if not _css(step.get("into")):
            out.append(f"{where}: type needs into, the field's CSS selector")
        if "cps" in step and not (_is_num(step["cps"]) and step["cps"] > 0):
            out.append(f"{where}: cps must be more than 0")
    if kind == "set":
        out += _set_problems(where, step)
    if kind == "key":
        if not (isinstance(step["key"], str) and step["key"].strip()):
            out.append(f"{where}: key needs the label to show, like Return or a shortcut")
        if "at" in step and not _css(step["at"]):
            out.append(f"{where}: at needs the CSS selector of the focused element")
        if "then" in step:
            out += _action_problems(where, step["then"], screens)
    if kind == "wait" and not (_is_num(step["wait"]) and step["wait"] >= 0):
        out.append(f"{where}: wait must be seconds, 0 or more")
    if "pause" in step and not (_is_num(step["pause"]) and step["pause"] >= 0):
        out.append(f"{where}: pause must be seconds, 0 or more")
    extra = {"then"} if kind not in ("click", "tap", "key") else set()
    extra |= {"at"} if kind != "key" else set()
    extra |= {"into", "cps"} if kind != "type" else set()
    extra |= set(SET_OPS) if kind != "set" else set()
    bad = sorted(set(step) & extra)
    if bad:
        out.append(f"{where}: {kind} does not take {', '.join(bad)}")
    return out


def parse_flow(doc: dict) -> dict:
    """The flow with its defaults (`pointer` arrow, each step's `pause` 0.8 s, `cps` 14) and `w`, `h` from
    `size`; ValueError names every problem."""
    if not isinstance(doc, dict):
        raise ValueError("flow.json must be an object")
    problems = []
    size = parse_size(doc.get("size", "1440x900"))
    if not size:
        problems.append("size must be WIDTHxHEIGHT, like 1440x900")
    pointer = doc.get("pointer", "arrow")
    if pointer not in ("arrow", "finger"):
        problems.append("pointer must be arrow or finger")
    screens = doc.get("screens")
    if not (isinstance(screens, list) and screens and all(isinstance(s, str) and s for s in screens)):
        problems.append("screens must list the data-screen ids of index.html")
        screens = []
    if len(set(screens)) != len(screens):
        problems.append("screens lists an id twice")
    start = doc.get("start", screens[0] if screens else None)
    if start not in screens:
        problems.append(f"start id {start!r} is not in screens")
    steps = doc.get("steps")
    if not isinstance(steps, list):
        problems.append("steps must be a list")
        steps = []
    problems += [p for i, step in enumerate(steps) for p in _step_problems(i, step, screens)]
    if problems:
        raise ValueError("; ".join(problems))
    out_steps = []
    for step in steps:
        s = {**step, "pause": step.get("pause", DEFAULT_PAUSE)}
        if "type" in s:
            s["cps"] = s.get("cps", DEFAULT_CPS)
        out_steps.append(s)
    return {**doc, "size": f"{size[0]}x{size[1]}", "w": size[0], "h": size[1], "pointer": pointer,
            "screens": screens, "start": start, "steps": out_steps}


def _kind(step: dict) -> str:
    return next(k for k in STEP_KEYS if k in step)


def flow_times(flow: dict, press: float = 0.15) -> list[dict]:
    """Each step's start `t` and `end`: step 0 starts at 0.5 s, a step's `pause` is the wait after it."""
    t = FIRST_STEP
    out = []
    for i, step in enumerate(flow["steps"]):
        kind = _kind(step)
        if kind == "type":
            length = len(step["type"]) / step.get("cps", DEFAULT_CPS)
            target = step["into"]
        elif kind in ("click", "tap"):
            length, target = press, step[kind]
        elif kind == "key":
            length, target = press, step.get("at")
        elif kind == "wait":
            length, target = float(step["wait"]), None
        else:
            length, target = 0.0, step[kind]
        end = round(t + length, 3)
        out.append({**step, "i": i, "t": round(t, 3), "end": end, "kind": kind, "target": target})
        t = end + step.get("pause", DEFAULT_PAUSE)
    return out


def flow_duration(times: list[dict]) -> float:
    """The last step's end plus a 1 s tail."""
    return round((times[-1]["end"] if times else FIRST_STEP) + TAIL, 3)


def measured_log(times: list[dict], rects: dict[int, dict], viewport: dict) -> dict:
    """The click log of a flow: a click or tap at its target's center at its `t`, one `key` event per typed
    character at the field's center, one `key` event for a key step with an `at` (so the camera follows a
    keyboard-driven UI). `rects` maps a step index to its target's {x, y, w, h}."""
    events = []
    missing = []
    for s in times:
        if s["kind"] not in ("click", "tap", "type", "key") or (s["kind"] == "key" and not s["target"]):
            continue
        r = rects.get(s["i"])
        if r is None:
            missing.append(f"step {s['i']} ({s['kind']} {s['target']}) has no measured rect")
            continue
        cx, cy = r["x"] + r["w"] / 2, r["y"] + r["h"] / 2
        if s["kind"] == "type":
            cps = s.get("cps", DEFAULT_CPS)
            events += [{"t": round(s["t"] + k / cps, 3), "kind": "key", "x": cx, "y": cy} for k in range(len(s["type"]))]
        else:
            events.append({"t": s["t"], "kind": s["kind"], "x": cx, "y": cy, **({"hand": True} if r.get("hand") else {})})
    if missing:
        raise ValueError("; ".join(missing))
    events.sort(key=lambda e: e["t"])
    return {"viewport": {"w": viewport["w"], "h": viewport["h"], "dpr": viewport["dpr"]},
            "duration": flow_duration(times), "events": events}
