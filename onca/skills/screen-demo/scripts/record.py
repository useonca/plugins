#!/usr/bin/env python3
"""Record a web page in a headless Chrome with its own profile (rung 2 for the web; free, no permission).

usage: record.py run STEPS.json --out REC [--size 1440x900] [--dpr 2] [--headed --profile DIR]
       record.py capture --port P --out REC [--seconds 20]

`run` opens a new Chrome (headless, its own throwaway profile unless --profile), plays the steps (goto,
click, type, scroll, wait, key) with a real mouse path, and records Chrome's own screencast. `capture`
records a Chrome that is already open with a debugging port (for example one a browser-use session drives).
Both write REC/frames/, frames.json, events.jsonl, raw.mp4 (30 fps) and clicks.json for polish.py.
Typed text never reaches a log.
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent))
import cdp  # noqa: E402
import record_core  # noqa: E402
import shared  # noqa: E402

KEYS = {
    "Enter": ("Enter", 13, "\r"), "Tab": ("Tab", 9, ""), "Escape": ("Escape", 27, ""),
    "Backspace": ("Backspace", 8, ""), "Space": ("Space", 32, " "), "ArrowDown": ("ArrowDown", 40, ""),
    "ArrowUp": ("ArrowUp", 38, ""), "ArrowLeft": ("ArrowLeft", 37, ""), "ArrowRight": ("ArrowRight", 39, ""),
}


class Recorder:
    """One page under the screencast: frames saved and acknowledged at once, page events kept."""

    def __init__(self, client: cdp.Cdp, rec: Path, size: tuple[int, int], dpr: float):
        self.c, self.rec, self.size, self.dpr = client, rec, size, dpr
        self.frames: list[dict] = []
        self.events: list[dict] = []
        self.loaded = False
        self.mouse = (size[0] / 2, size[1] / 2)
        (rec / "frames").mkdir(parents=True, exist_ok=True)
        self.events_file = open(rec / "events.jsonl", "w")

    def setup(self, attach: bool = False) -> None:
        self.c.call("Page.enable")
        self.c.call("Runtime.enable")
        self.c.call("Runtime.addBinding", name="__oncaRec")
        self.c.call("Page.addScriptToEvaluateOnNewDocument", source=record_core.LISTENER_JS)
        self.c.call("Page.addScriptToEvaluateOnNewDocument", source=record_core.HIDE_DEV_JS)
        if attach:
            self.c.call("Runtime.evaluate", expression=record_core.LISTENER_JS)
            self.c.call("Runtime.evaluate", expression=record_core.HIDE_DEV_JS)
        else:
            w, h = self.size
            self.c.call("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=self.dpr, mobile=False)
        self.drain()

    def start(self) -> None:
        w, h = self.size
        self.c.call("Page.startScreencast", format="jpeg", quality=85, maxWidth=int(w * self.dpr),
                    maxHeight=int(h * self.dpr), everyNthFrame=1)

    def handle(self, ev: dict) -> None:
        method, params = ev.get("method"), ev.get("params", {})
        if method == "Page.screencastFrame":
            self.c.send("Page.screencastFrameAck", sessionId=params["sessionId"])
            ts = params["metadata"].get("timestamp") or time.time()
            name = f"frames/{len(self.frames):05d}.jpg"
            (self.rec / name).write_bytes(base64.b64decode(params["data"]))
            self.frames.append({"file": name, "ts": ts})
        elif method == "Runtime.bindingCalled" and params.get("name") == "__oncaRec":
            e = record_core.parse_event(params.get("payload", ""))
            if e:
                self.events.append(e)
                self.events_file.write(json.dumps(e) + "\n")
        elif method == "Page.loadEventFired":
            self.loaded = True

    def drain(self) -> None:
        while self.c.events:
            self.handle(self.c.events.pop(0))

    def pump(self, seconds: float) -> None:
        """Handle what arrives for `seconds`."""
        deadline = time.monotonic() + seconds
        self.drain()
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                return
            ev = self.c.next_event(left)
            if ev:
                self.handle(ev)

    def call(self, method: str, **params) -> dict:
        out = self.c.call(method, **params)
        self.drain()
        return out

    # ------------------------------------------------------------ steps

    def goto(self, url: str) -> None:
        self.loaded = False
        self.call("Page.navigate", url=url)
        deadline = time.monotonic() + 30
        while not self.loaded and time.monotonic() < deadline:
            self.pump(0.1)
        if not self.loaded:
            shared.log(f"warning: {url} did not finish loading in 30 s; going on")
        self.pump(0.3)
        self.check_clean(url)

    def check_clean(self, where: str) -> None:
        """Stop when a framework's dev badge or overlay would be on video (record a production build)."""
        visible = self.call("Runtime.evaluate", expression=record_core.DEV_CHECK_JS, returnByValue=True)
        badges = record_core.dev_badges(visible.get("result", {}).get("value") or [])
        if badges:
            print(f"{where}: {', '.join(badges)} on the page; record a production build or the live URL", file=sys.stderr)
            raise SystemExit(1)

    def locate(self, i: int, css: str) -> tuple[float, float]:
        js = (
            "(() => { const el = document.querySelector(%s); if (!el) return null;"
            " const r0 = el.getBoundingClientRect();"
            " if (r0.top < 0 || r0.bottom > innerHeight || r0.left < 0 || r0.right > innerWidth)"
            "   el.scrollIntoView({block: 'center', inline: 'center', behavior: 'smooth'});"
            " return true; })()" % json.dumps(css)
        )
        found = self.call("Runtime.evaluate", expression=js, returnByValue=True).get("result", {}).get("value")
        if not found:
            print(f"step {i}: no element matches {css}", file=sys.stderr)
            raise SystemExit(1)
        self.pump(0.6)  # a smooth scroll into view, if one was needed
        js = ("(() => { const r = document.querySelector(%s).getBoundingClientRect();"
              " return [r.left + r.width / 2, r.top + r.height / 2]; })()" % json.dumps(css))
        x, y = self.call("Runtime.evaluate", expression=js, returnByValue=True)["result"]["value"]
        return x, y

    def move_to(self, x: float, y: float) -> None:
        """A human mouse path: an eased glide of about 0.45 s, one mouse event every 30 ms."""
        x0, y0 = self.mouse
        dist = math.hypot(x - x0, y - y0)
        steps = max(1, min(18, int(dist / 40)))
        for k in range(1, steps + 1):
            p = k / steps
            e = -(math.cos(math.pi * p) - 1) / 2
            self.call("Input.dispatchMouseEvent", type="mouseMoved", x=x0 + (x - x0) * e, y=y0 + (y - y0) * e)
            self.pump(0.45 / steps)
        self.mouse = (x, y)

    def click(self, x: float, y: float) -> None:
        self.move_to(x, y)
        self.pump(0.12)
        for kind in ("mousePressed", "mouseReleased"):
            self.call("Input.dispatchMouseEvent", type=kind, x=x, y=y, button="left", clickCount=1)
            self.pump(0.06)

    def type(self, text: str, cps: float = 14) -> None:
        for ch in text:
            self.call("Input.dispatchKeyEvent", type="keyDown", text=ch, unmodifiedText=ch)
            self.call("Input.dispatchKeyEvent", type="keyUp")
            self.pump(1 / cps)

    def key(self, name: str) -> None:
        key, code, text = KEYS.get(name, (name, 0, name if len(name) == 1 else ""))
        params = {"key": key, "code": key, "windowsVirtualKeyCode": code}
        self.call("Input.dispatchKeyEvent", type="keyDown", text=text, **params)
        self.call("Input.dispatchKeyEvent", type="keyUp", **params)

    def scroll(self, dy: float, at: tuple[float, float] | None) -> None:
        x, y = at or self.mouse
        if at:
            self.move_to(x, y)
        room = self.call("Runtime.evaluate", expression=record_core.scroll_room_js(x, y), returnByValue=True)
        down, up = room.get("result", {}).get("value") or [0, 0]
        move = record_core.scroll_amount(dy, down, up)
        if move != dy:
            shared.log(f"scroll {dy:g} px: the page has {down:g} px below and {up:g} px above; "
                       + ("skipped" if not move else f"moving {move:g} px"))
        if not move:
            return
        dy = move
        pieces = max(1, int(abs(dy) / 60))
        for _ in range(pieces):
            self.call("Input.dispatchMouseEvent", type="mouseWheel", x=x, y=y, deltaX=0, deltaY=dy / pieces)
            self.pump(0.03)

    def play(self, steps: list[dict]) -> None:
        for i, s in enumerate(steps):
            if "goto" in s:
                shared.log(f"step {i}: goto {s['goto']}")
                self.goto(s["goto"])
            elif "click" in s:
                target = s["click"]
                shared.log(f"step {i}: click {target}")
                x, y = target if isinstance(target, list) else self.locate(i, target)
                self.click(x, y)
            elif "type" in s:
                if s.get("into"):
                    self.click(*self.locate(i, s["into"]))
                shared.log(f"step {i}: type {len(s['type'])} characters")
                self.type(s["type"])
            elif "scroll" in s:
                shared.log(f"step {i}: scroll {s['scroll']}")
                self.scroll(s["scroll"], tuple(s["at"]) if s.get("at") else None)
            elif "wait" in s:
                shared.log(f"step {i}: wait {s['wait']} s")
                self.pump(s["wait"])
            elif "key" in s:
                shared.log(f"step {i}: key {s['key']}")
                self.key(s["key"])
            self.pump(s["pause"])
            self.check_clean(f"step {i}")  # a build error can appear mid-recording (a hot reload)

    def write(self, start_ts: float, stop_ts: float) -> None:
        self.events_file.close()
        rec = self.rec
        (rec / "frames.json").write_text(json.dumps(self.frames, indent=0))
        if not self.frames:
            print("no frame arrived from Chrome's screencast", file=sys.stderr)
            raise SystemExit(1)
        start_ts = self.frames[0]["ts"]  # raw.mp4 starts at the first frame, so the click log does too
        frames = [f for f in self.frames if f["ts"] <= stop_ts]
        (rec / "frames.ffconcat").write_text(record_core.ffconcat(frames, stop_ts))
        log = record_core.click_log(self.events, start_ts, stop_ts, {"w": self.size[0], "h": self.size[1], "dpr": self.dpr})
        (rec / "clicks.json").write_text(json.dumps(log, indent=1))
        shared.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
                    "-i", str(rec / "frames.ffconcat"), "-t", f"{stop_ts - start_ts:.3f}",
                    "-vf", "fps=30,scale=trunc(iw/2)*2:trunc(ih/2)*2:out_range=tv,format=yuv420p",
                    "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", "-r", "30", "-movflags", "+faststart",
                    str(rec / "raw.mp4")])
        shared.log(f"{len(frames)} frames, {len(log['events'])} events, {log['duration']} s -> {rec / 'raw.mp4'}")


def _local(url: str) -> bool:
    host = urlparse(url).hostname or ""
    return host in ("localhost", "127.0.0.1", "::1") or host.endswith(".localhost")


def cmd_run(a) -> None:
    try:
        steps = record_core.parse_steps(json.loads(Path(a.steps).read_text()))
    except FileNotFoundError:
        shared.bad_input([f"no steps file at {a.steps}"])
    except ValueError as e:
        shared.bad_input(str(e))
    size = shared.parse_size(a.size)
    rec = Path(a.out)
    rec.mkdir(parents=True, exist_ok=True)
    with cdp.chrome(size, dpr=a.dpr, headed=a.headed, profile=a.profile) as client:
        r = Recorder(client, rec, size, a.dpr)
        r.setup()
        if any(_local(s.get("goto", "")) for s in steps):
            r.call("Security.setIgnoreCertificateErrors", ignore=True)  # a local dev certificate
        if steps and "goto" in steps[0]:
            shared.log(f"step 0: goto {steps[0]['goto']} (before the recording starts)")
            r.goto(steps[0]["goto"])
            r.pump(0.5)
            steps = [{"wait": 0, "pause": steps[0]["pause"]}] + steps[1:]
        start_ts = time.time()
        r.start()
        r.pump(0.4)
        r.play(steps)
        r.pump(1.0)
        stop_ts = time.time()
        r.call("Page.stopScreencast")
        r.write(start_ts, stop_ts)


def cmd_capture(a) -> None:
    rec = Path(a.out)
    rec.mkdir(parents=True, exist_ok=True)
    try:
        client = cdp.Cdp(cdp.page_ws_url(a.port))
    except OSError as e:
        print(f"no Chrome with a debugging port on {a.port}: {e}", file=sys.stderr)
        raise SystemExit(1)
    try:
        vp = client.call("Runtime.evaluate", expression="[innerWidth, innerHeight, devicePixelRatio]",
                         returnByValue=True)["result"]["value"]
        r = Recorder(client, rec, (int(vp[0]), int(vp[1])), float(vp[2]))
        r.setup(attach=True)
        start_ts = time.time()
        r.start()
        shared.log(f"recording {a.seconds} s of the open page (Ctrl-C stops early)")
        try:
            r.pump(a.seconds)
        except KeyboardInterrupt:
            pass
        stop_ts = time.time()
        r.call("Page.stopScreencast")
        r.write(start_ts, stop_ts)
    except (ConnectionError, TimeoutError, RuntimeError) as e:
        print(f"Chrome failed: {e}", file=sys.stderr)
        raise SystemExit(1)
    finally:
        client.close()


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Record a web page in a headless Chrome with its own profile.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="open a new Chrome, play STEPS.json and record it")
    r.add_argument("steps")
    r.add_argument("--out", required=True)
    r.add_argument("--size", default="1440x900")
    r.add_argument("--dpr", type=float, default=2)
    r.add_argument("--headed", action="store_true", help="show the window (only with the founder's yes)")
    r.add_argument("--profile", help="a Chrome profile folder of its own (default: a throwaway one)")
    c = sub.add_parser("capture", help="record a Chrome already open with a debugging port")
    c.add_argument("--port", type=int, required=True)
    c.add_argument("--out", required=True)
    c.add_argument("--seconds", type=float, default=20)
    a = ap.parse_args(argv)
    cmd_run(a) if a.cmd == "run" else cmd_capture(a)


if __name__ == "__main__":
    main()
