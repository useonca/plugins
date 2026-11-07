#!/usr/bin/env python3
"""Render a flow on a screen rebuilt from the product's source (rung 1, the default footage route).

usage: flow.py render FLOW_DIR --out REC [--dpr 2] [--draft]

FLOW_DIR holds the client's index.html (its <body> holds the screens, each an element with a `data-screen`
id, styled with the product's real tokens and the kit's classes) and flow.json (the steps). flow.py copies the
folder and assets/kit/ into REC/flow-hf/, wraps the body in the composition root (scaled by --dpr, so text is
sharp under the polish's zoom), writes flow-data.js, measures each pressed target in a headless Chrome with
its own profile, writes REC/clicks.json and renders REC/raw.mp4. Then: polish.py REC --out clip.mp4.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import cdp  # noqa: E402
import flow_core  # noqa: E402
import shared  # noqa: E402

KIT = Path(__file__).resolve().parents[1] / "assets" / "kit"


def page_html(client: str, w: int, h: int, dpr: float, duration: float) -> str:
    """The client's page inside the composition root: kit first, the client's own head after it."""
    head = re.search(r"<head[^>]*>(.*?)</head>", client, re.S | re.I)
    body = re.search(r"<body[^>]*>(.*?)</body>", client, re.S | re.I)
    head_inner = head.group(1) if head else ""
    body_inner = body.group(1) if body else client
    W, H = round(w * dpr), round(h * dpr)
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="stylesheet" href="kit/kit.css" />
{head_inner}
    <style>
      html, body {{ margin: 0; padding: 0; width: {W}px; height: {H}px; overflow: hidden; background: #000; }}
      #main {{ position: relative; width: {W}px; height: {H}px; overflow: hidden; }}
      #onca-flow {{ position: absolute; left: 0; top: 0; width: {w}px; height: {h}px; zoom: {dpr:g}; }}
    </style>
  </head>
  <body>
    <div id="main" data-composition-id="main" data-start="0" data-duration="{duration}" data-width="{W}" data-height="{H}" data-no-timeline>
      <div id="onca-flow">
{body_inner}
      </div>
    </div>
    <script src="flow-data.js"></script>
    <script src="kit/flow.js"></script>
  </body>
</html>
"""


def measure(index: Path, times: list[dict], size: tuple[int, int]) -> dict[int, dict]:
    """Each pressed step's target box, from the page itself at that step's time."""
    rects: dict[int, dict] = {}
    with cdp.chrome(size) as client:
        client.call("Page.enable")
        client.call("Emulation.setDeviceMetricsOverride", width=size[0], height=size[1], deviceScaleFactor=1, mobile=False)
        client.call("Page.navigate", url=index.resolve().as_uri())
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            ev = client.next_event(0.5)
            if ev and ev.get("method") == "Page.loadEventFired":
                break
        client.call("Runtime.evaluate", expression="document.fonts.ready.then(() => true)", awaitPromise=True)
        ok = client.call("Runtime.evaluate", expression="typeof window.OncaFlow", returnByValue=True)["result"].get("value")
        if ok != "object":
            print("the flow page did not load kit/flow.js (see the browser console of REC/flow-hf/index.html)", file=sys.stderr)
            raise SystemExit(1)
        for s in times:
            if s["kind"] not in ("click", "tap", "type", "key") or not s["target"]:
                continue
            expr = f"(OncaFlow.seek({s['t']}), OncaFlow.rect({s['i']}))"
            r = client.call("Runtime.evaluate", expression=expr, returnByValue=True)["result"].get("value")
            if r:
                rects[s["i"]] = r
    return rects


def render(a) -> None:
    src = Path(a.flow_dir)
    problems = []
    if not (src / "index.html").exists():
        problems.append(f"{src}/index.html is missing")
    if not (src / "flow.json").exists():
        problems.append(f"{src}/flow.json is missing")
    if problems:
        shared.bad_input(problems)
    try:
        flow = flow_core.parse_flow(json.loads((src / "flow.json").read_text()))
    except ValueError as e:
        shared.bad_input(str(e))
    times = flow_core.flow_times(flow)
    duration = flow_core.flow_duration(times)
    w, h, dpr = flow["w"], flow["h"], a.dpr
    rec = Path(a.out)
    proj = rec / "flow-hf"
    if proj.exists():
        shutil.rmtree(proj)
    shutil.copytree(src, proj, ignore=shutil.ignore_patterns("out", "REC", "*-hf", ".DS_Store"))
    shutil.copytree(KIT, proj / "kit")
    data = {"w": w, "h": h, "dpr": dpr, "start": flow["start"], "screens": flow["screens"], "steps": times}
    (proj / "flow-data.js").write_text("window.FLOW_DATA = " + json.dumps(data) + ";\n")
    (proj / "index.html").write_text(page_html((src / "index.html").read_text(), w, h, dpr, duration))
    shared.log(f"{len(times)} steps, {duration} s, {w}x{h} at {dpr:g}x")
    rects = measure(proj / "index.html", times, (round(w * dpr), round(h * dpr)))
    try:
        log = flow_core.measured_log(times, rects, {"w": w, "h": h, "dpr": dpr})
    except ValueError as e:
        print(f"{e} (is the selector right and its screen shown at that step?)", file=sys.stderr)
        raise SystemExit(2)
    log["pointer"] = flow["pointer"]
    (rec / "clicks.json").write_text(json.dumps(log, indent=1))
    shared.render(proj, rec / "raw.mp4", a.draft)
    shared.log(f"{len(log['events'])} events -> {rec / 'clicks.json'}, {rec / 'raw.mp4'}")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Render a flow on a screen rebuilt from the product's source.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render", help="measure and render FLOW_DIR into REC (raw.mp4 + clicks.json)")
    r.add_argument("flow_dir")
    r.add_argument("--out", required=True)
    r.add_argument("--dpr", type=float, default=2)
    r.add_argument("--draft", action="store_true")
    a = ap.parse_args(argv)
    render(a)


if __name__ == "__main__":
    main()
