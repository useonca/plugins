"""The pure half of record.py: the Chrome command, the steps file, the page's event payloads, the frame list
and the click log. No I/O here; record.py and cdp.py do it.

Times: `ts` is epoch seconds (the screencast's `metadata.timestamp` and the page's `Date.now() / 1000`
share that clock); a click log's `t` is seconds from the recording's start, rounded to the millisecond.
"""

from __future__ import annotations

import json

DEFAULT_PAUSE = 0.8
MIN_FRAME = 1 / 30
EVENT_KINDS = ("click", "move", "key", "scroll")

# Added with Page.addScriptToEvaluateOnNewDocument, so it runs in every page before the page's own code.
# It reports where the pointer is and where a key was pressed (the focused field's center), never which key:
# typed text stays out of every log.
LISTENER_JS = r"""
(() => {
  if (window.__oncaRecInstalled) return;
  window.__oncaRecInstalled = true;
  const HAND = "a[href], button, [role=button], [role=link], summary, label, select, input[type=submit], input[type=checkbox], input[type=radio]";
  const send = (kind, x, y, hand) => {
    if (typeof window.__oncaRec !== "function") return;
    const ev = { kind, x: Math.round(x), y: Math.round(y), ts: Date.now() / 1000 };
    if (hand) ev.hand = true;
    window.__oncaRec(JSON.stringify(ev));
  };
  const overLink = (e) => {
    const t = e.target;
    return !!(t && t.closest && (t.closest(HAND) || getComputedStyle(t).cursor === "pointer"));
  };
  const opts = { capture: true, passive: true };
  addEventListener("pointerdown", (e) => send("click", e.clientX, e.clientY, overLink(e)), opts);
  addEventListener("pointermove", (e) => send("move", e.clientX, e.clientY, overLink(e)), opts);
  addEventListener("wheel", (e) => send("scroll", e.clientX, e.clientY), opts);
  addEventListener("keydown", () => {
    const el = document.activeElement;
    const r = el && el !== document.body ? el.getBoundingClientRect() : null;
    if (r) send("key", r.left + r.width / 2, r.top + r.height / 2);
    else send("key", innerWidth / 2, innerHeight / 2);
  }, opts);
})();
"""


def chrome_command(chrome: str, port: int, profile: str, size: tuple[int, int], headed: bool = False,
                   dpr: float = 1) -> list[str]:
    """Chrome with its own profile and a debugging port; headless unless asked. A `dpr` above 1 forces that
    device scale, without which the screencast sends 1x frames even under an emulated scale."""
    w, h = size
    cmd = [chrome]
    if not headed:
        cmd.append("--headless=new")
    if dpr != 1:
        cmd.append(f"--force-device-scale-factor={dpr:g}")
    cmd += [
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile}",
        f"--window-size={w},{h}",
        "--no-first-run",
        "--no-default-browser-check",
        "--hide-scrollbars",
        "about:blank",
    ]
    return cmd


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _is_point(v) -> bool:
    return isinstance(v, list) and len(v) == 2 and all(_is_num(n) for n in v)


_STEP_KEYS = {"goto", "click", "type", "scroll", "wait", "key"}
_EXTRA_KEYS = {"goto": set(), "click": set(), "type": {"into"}, "scroll": {"at"}, "wait": set(), "key": set()}


def _step_problems(i: int, step) -> list[str]:
    if not isinstance(step, dict):
        return [f"step {i}: must be an object"]
    kinds = [k for k in step if k in _STEP_KEYS]
    unknown = [k for k in step if k not in _STEP_KEYS and k not in ("pause", "into", "at")]
    if unknown:
        return [f"step {i}: unknown step {', '.join(unknown)}"]
    if len(kinds) != 1:
        return [f"step {i}: needs exactly one of {', '.join(sorted(_STEP_KEYS))}"]
    kind, value = kinds[0], step[kinds[0]]
    out = []
    extra = set(step) - {kind, "pause"} - _EXTRA_KEYS[kind]
    if extra:
        out.append(f"step {i}: {kind} does not take {', '.join(sorted(extra))}")
    if kind == "goto" and not (isinstance(value, str) and value):
        out.append(f"step {i}: goto needs a URL")
    if kind == "click" and not ((isinstance(value, str) and value) or _is_point(value)):
        out.append(f"step {i}: click needs a CSS selector or [x, y]")
    if kind == "type":
        if not isinstance(value, str):
            out.append(f"step {i}: type needs text")
        if "into" in step and not (isinstance(step["into"], str) and step["into"]):
            out.append(f"step {i}: into needs a CSS selector")
    if kind == "scroll":
        if not _is_num(value):
            out.append(f"step {i}: scroll needs a number of pixels")
        if "at" in step and not _is_point(step["at"]):
            out.append(f"step {i}: at needs [x, y]")
    if kind == "wait" and not (_is_num(value) and value >= 0):
        out.append(f"step {i}: wait needs seconds, 0 or more")
    if kind == "key" and not (isinstance(value, str) and value):
        out.append(f"step {i}: key needs a key name such as Enter")
    if "pause" in step and not (_is_num(step["pause"]) and step["pause"] >= 0):
        out.append(f"step {i}: pause must be seconds, 0 or more")
    return out


def parse_steps(doc: list) -> list[dict]:
    """The steps of a recording, each with its `pause` (default 0.8 s); ValueError names every bad step."""
    if not isinstance(doc, list):
        raise ValueError("steps must be a list")
    problems = [p for i, step in enumerate(doc) for p in _step_problems(i, step)]
    if problems:
        raise ValueError("; ".join(problems))
    return [{**step, "pause": step.get("pause", DEFAULT_PAUSE)} for step in doc]


def parse_event(payload: str) -> dict | None:
    """One event the page sent through the binding, or None when it is not one."""
    try:
        d = json.loads(payload)
    except (TypeError, ValueError):
        return None
    if not isinstance(d, dict) or d.get("kind") not in EVENT_KINDS:
        return None
    if not all(_is_num(d.get(k)) for k in ("x", "y", "ts")):
        return None
    out = {"kind": d["kind"], "x": d["x"], "y": d["y"], "ts": d["ts"]}
    if d.get("hand") is True:
        out["hand"] = True
    return out


def ffconcat(frames: list[dict], stop_ts: float) -> str:
    """An ffconcat list holding each frame until the next one (the last until `stop_ts`), at least one 30 fps
    frame each; the last file is listed again, as the concat demuxer needs for the last duration to count."""
    frames = sorted(frames, key=lambda f: f["ts"])
    lines = ["ffconcat version 1.0"]
    for k, f in enumerate(frames):
        nxt = frames[k + 1]["ts"] if k + 1 < len(frames) else stop_ts
        lines.append(f"file '{f['file']}'")
        lines.append(f"duration {max(MIN_FRAME, nxt - f['ts']):.6f}")
    if frames:
        lines.append(f"file '{frames[-1]['file']}'")
    return "\n".join(lines) + "\n"


def click_log(events: list[dict], start_ts: float, stop_ts: float, viewport: dict) -> dict:
    """The click log every rung writes (`clicks.json`): events inside the recording, relative to its start."""
    kept = [
        {"t": round(e["ts"] - start_ts, 3), "kind": e["kind"], "x": e["x"], "y": e["y"], **({"hand": True} if e.get("hand") else {})}
        for e in events
        if start_ts <= e["ts"] <= stop_ts
    ]
    kept.sort(key=lambda e: e["t"])
    return {
        "viewport": {"w": viewport["w"], "h": viewport["h"], "dpr": viewport["dpr"]},
        "duration": round(stop_ts - start_ts, 3),
        "events": kept,
    }


# ---------------------------------------------------------------- what never goes on video

# Framework dev badges and overlays a dev server draws over the page: selector -> the name a log shows.
DEV_OVERLAYS = {
    "nextjs-portal": "Next.js dev indicator",
    "[data-nextjs-toast]": "Next.js dev toast",
    "[data-nextjs-dev-tools-button]": "Next.js dev tools button",
    "#__next-build-watcher": "Next.js build indicator",
    "astro-dev-toolbar": "Astro dev toolbar",
    "#nuxt-devtools-container": "Nuxt devtools",
    "#svelte-inspector-host": "Svelte inspector",
    ".tsqd-parent-container": "TanStack Query devtools",
}

# A build error drawn over the page: never hidden, the recording stops (the app under it is broken).
DEV_ERRORS = {
    "vite-error-overlay": "Vite error overlay",
    "#webpack-dev-server-client-overlay": "webpack dev server overlay",
}

# Injected before the page's own code: a style that hides every known dev badge (never an error overlay).
HIDE_DEV_JS = (
    "(() => { const css = %s; const add = () => { if (document.getElementById('onca-hide-dev')) return;"
    " const s = document.createElement('style'); s.id = 'onca-hide-dev'; s.textContent = css;"
    " (document.head || document.documentElement).appendChild(s); };"
    " if (document.documentElement) add(); document.addEventListener('DOMContentLoaded', add); })();"
    % json.dumps(", ".join(DEV_OVERLAYS) + " { display: none !important; visibility: hidden !important; }")
)

# Returns the selectors of dev badges still drawn (the hide style lost, e.g. to an inline !important) and of
# build error overlays.
DEV_CHECK_JS = (
    "(() => %s.filter((sel) => Array.from(document.querySelectorAll(sel))"
    ".some((el) => el.getClientRects().length > 0 && getComputedStyle(el).visibility !== 'hidden')))()"
    % json.dumps(list(DEV_OVERLAYS) + list(DEV_ERRORS))
)


def dev_badges(visible: list) -> list:
    """The names of the dev overlays still visible (from DEV_CHECK_JS); empty means the frame is clean."""
    names = {**DEV_OVERLAYS, **DEV_ERRORS}
    return [names[sel] for sel in visible if sel in names]


# ---------------------------------------------------------------- scrolling a page that can scroll


def scroll_room_js(x: float, y: float) -> str:
    """[room down, room up] in CSS pixels of the scroller under (x, y): its nearest scrollable ancestor, else
    the page."""
    return (
        "(() => { let el = document.elementFromPoint(%s, %s);"
        " while (el && el !== document.body && el !== document.documentElement) {"
        "  const o = getComputedStyle(el).overflowY;"
        "  if ((o === 'auto' || o === 'scroll') && el.scrollHeight > el.clientHeight + 1)"
        "   return [el.scrollHeight - el.clientHeight - el.scrollTop, el.scrollTop];"
        "  el = el.parentElement; }"
        " const s = document.scrollingElement || document.documentElement;"
        " return [s.scrollHeight - innerHeight - scrollY, scrollY]; })()" % (round(x, 1), round(y, 1))
    )


def scroll_amount(requested: float, room_down: float, room_up: float, min_move: float = 40.0) -> float:
    """How far a scroll step really moves: clamped to the room the page has, and 0 when that is under
    `min_move` px (a page with a few pixels of overflow only shudders on screen)."""
    room = room_down if requested > 0 else room_up
    move = min(abs(requested), max(0.0, room))
    return 0.0 if move < min_move else (move if requested > 0 else -move)
