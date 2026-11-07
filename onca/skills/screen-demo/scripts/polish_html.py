"""The polish composition: the recording on a styled stage, a camera that zooms to each click, an enlarged,
smoothed cursor (or a finger dot) and a ripple on each press. Pure: it returns the page's text.

Every state comes from the engine's time in an `hf-seek` listener (no GSAP, no clock), so any frame renders
on its own; the root's `data-duration` gives the length and the engine's motion blur smears fast moves.
"""

from __future__ import annotations

import json

POINTERS = ("arrow", "finger")

# The macOS look, drawn by us: a slim black arrow with a white outline and a soft shadow,
# its tip at (0, 0) of a 24 x 24 box; a white pointing hand with a dark outline, its fingertip at (0, 0), shown
# over links and buttons. Vector, so crisp at any zoom.
ARROW_SVG = (
    '<svg class="ptr ptr-arrow" viewBox="-1.2 -1.2 24 24" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg">'
    '<path d="M0 0 L0 17.2 L4.1 13.3 L6.9 19.8 L9.9 18.5 L7.2 12.2 L12.8 12.2 Z" fill="#000" stroke="#fff" '
    'stroke-width="1.5" stroke-linejoin="round" paint-order="stroke"/></svg>'
)
HAND_SVG = (
    '<svg class="ptr ptr-hand" viewBox="-7.2 -1.2 24 24" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg">'
    '<path d="M-1.6 1.6 C-1.6 0.7 -0.9 0 0 0 C0.9 0 1.6 0.7 1.6 1.6 L1.6 7.4 C1.9 7.1 2.3 7 2.8 7 C3.6 7 4.2 7.5 4.3 8.2 '
    'C4.6 7.9 5 7.8 5.4 7.8 C6.2 7.8 6.8 8.3 6.9 9 C7.2 8.8 7.5 8.7 7.9 8.7 C8.8 8.7 9.4 9.4 9.4 10.2 L9.4 14.4 '
    'C9.4 17.2 7.3 19.4 4.6 19.4 L2 19.4 C0.6 19.4 -0.7 18.7 -1.5 17.6 L-5.2 12.4 C-5.8 11.6 -5.6 10.6 -4.9 10.1 '
    'C-4.2 9.6 -3.2 9.7 -2.6 10.3 L-1.6 11.4 Z M2.6 12.2 L2.6 16.4 M5.1 12.2 L5.1 16.4 M7.5 12.2 L7.5 16.4" '
    'fill="#fff" stroke="#000" stroke-width="1.2" stroke-linejoin="round" stroke-linecap="round"/></svg>'
)

PAGE = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <style>
      html, body { margin: 0; padding: 0; width: __W__px; height: __H__px; overflow: hidden; background: __BG_A__; }
      #main { position: relative; width: __W__px; height: __H__px; overflow: hidden; }
      #bg { position: absolute; inset: 0; background: linear-gradient(135deg, __BG_A__ 0%, __BG_B__ 100%); }
      #cam { position: absolute; left: 0; top: 0; width: __W__px; height: __H__px; transform-origin: 0 0; }
      #stage { position: absolute; left: __SX__px; top: __SY__px; width: __SW__px; height: __SH__px;
               border-radius: __R__px; overflow: hidden; box-shadow: 0 30px 80px rgba(0,0,0,.45); background: #000; }
      #rec { position: absolute; left: 0; top: 0; width: 100%; height: 100%; object-fit: cover; }
      #cursor { position: absolute; left: 0; top: 0; width: __CS__px; height: __CS__px; transform-origin: 0 0; z-index: 5; }
      #cursor .ptr { position: absolute; inset: 0; filter: drop-shadow(0 1px 1.4px rgba(0,0,0,.38)) drop-shadow(0 3px 6px rgba(0,0,0,.18)); }
      #cursor .ptr-hand { display: none; transform: translateX(-25%); }  /* its fingertip on the click point, like the arrow's tip */
      #finger { position: absolute; left: 0; top: 0; width: 46px; height: 46px; margin: -23px 0 0 -23px; border-radius: 50%;
                background: radial-gradient(circle, rgba(255,255,255,.55) 0%, rgba(255,255,255,.32) 70%);
                border: 2px solid rgba(255,255,255,.85); box-sizing: border-box; opacity: 0; z-index: 5;
                box-shadow: 0 2px 12px rgba(0,0,0,.22), inset 0 0 0 1px rgba(0,0,0,.06); }
      .ripple { position: absolute; left: 0; top: 0; width: 64px; height: 64px; margin: -32px 0 0 -32px; border-radius: 50%;
                border: 3px solid rgba(255,255,255,.9); box-sizing: border-box; opacity: 0; z-index: 4; }
    </style>
  </head>
  <body>
    <div id="main" data-composition-id="main" data-start="0" data-duration="__DUR__" data-width="__W__" data-height="__H__"
         data-motion-blur="on" data-motion-blur-events="on" data-no-timeline>
      <div id="bg"></div>
      <div id="cam">
        <div id="stage">
          <video id="rec" class="clip" src="__VIDEO__" muted playsinline data-start="0" data-duration="__DUR__" data-track-index="0"></video>
        </div>
__RIPPLES__
        <div id="cursor"__CURSOR_STYLE__>__ARROW__</div>
        <div id="finger"></div>
      </div>
    </div>
    <script>
      (() => {
        const CAM = __CAM__;
        const CUR = __CUR__;
        const CLK = __CLK__;
        const L = __L__;
        const POINTER = "__POINTER__";
        const CS = __CS__;
        const cam = document.getElementById("cam");
        const cursor = document.getElementById("cursor");
        const arrowSvg = cursor.querySelector(".ptr-arrow");
        const handSvg = cursor.querySelector(".ptr-hand");
        const finger = document.getElementById("finger");
        const rings = Array.from(document.querySelectorAll(".ripple"));
        const cubic = (p) => (p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2);
        const sine = (p) => -(Math.cos(Math.PI * p) - 1) / 2;
        const clamp01 = (p) => Math.min(1, Math.max(0, p));
        const lerp = (a, b, p) => a + (b - a) * p;
        const px = (x) => L.x + x * L.scale;
        const py = (y) => L.y + y * L.scale;

        function camAt(t) {
          if (t <= CAM[0].t) return CAM[0];
          for (let i = 0; i < CAM.length - 1; i++) {
            const a = CAM[i], b = CAM[i + 1];
            if (t < b.t) {
              const p = cubic(clamp01((t - a.t) / (b.t - a.t)));
              return { scale: lerp(a.scale, b.scale, p), cx: lerp(a.cx, b.cx, p), cy: lerp(a.cy, b.cy, p) };
            }
          }
          return CAM[CAM.length - 1];
        }

        function cursorAt(t) {
          if (!CUR.length) return null;
          if (t <= CUR[0].t) return { x: CUR[0].x, y: CUR[0].y, hand: CUR[0].hand };
          for (let i = 0; i < CUR.length - 1; i++) {
            const a = CUR[i], b = CUR[i + 1];
            if (t < b.t) {
              if (t <= b.from || b.t <= b.from) return { x: a.x, y: a.y, hand: a.hand };
              const p = sine(clamp01((t - b.from) / (b.t - b.from)));
              return { x: lerp(a.x, b.x, p), y: lerp(a.y, b.y, p), hand: p > 0.85 ? b.hand : a.hand };
            }
          }
          const last = CUR[CUR.length - 1];
          return { x: last.x, y: last.y, hand: last.hand };
        }

        function renderAt(t) {
          const c = camAt(t);
          const tx = L.x + L.w / 2 - c.scale * px(c.cx);
          const ty = L.y + L.h / 2 - c.scale * py(c.cy);
          cam.style.transform = `translate(${tx}px, ${ty}px) scale(${c.scale})`;
          let press = 0;
          let near = 0;
          for (const k of CLK) {
            press = Math.max(press, 1 - Math.abs(t - k.t) / 0.12);
            near = Math.max(near, Math.min(clamp01((t - (k.t - 0.4)) / 0.15), clamp01((k.t + 0.45 - t) / 0.15)));
          }
          press = clamp01(press);
          const pos = cursorAt(t);
          if (pos && POINTER === "arrow") {
            const s = 1 - 0.18 * press;
            cursor.style.transform = `translate(${px(pos.x)}px, ${py(pos.y)}px) scale(${s})`;
            arrowSvg.style.display = pos.hand ? "none" : "block";
            handSvg.style.display = pos.hand ? "block" : "none";
          } else if (pos) {
            finger.style.transform = `translate(${px(pos.x)}px, ${py(pos.y)}px) scale(${1 - 0.15 * press})`;
            finger.style.opacity = String(0.6 * near);
          }
          CLK.forEach((k, i) => {
            const p = (t - k.t) / 0.45;
            const ring = rings[i];
            if (p < 0 || p >= 1) { ring.style.opacity = "0"; return; }
            ring.style.opacity = String(1 - p);
            ring.style.transform = `translate(${px(k.x)}px, ${py(k.y)}px) scale(${Math.max(0.001, p)})`;
          });
        }

        window.addEventListener("hf-seek", (e) => renderAt(e.detail.time));
        renderAt(0);
      })();
    </script>
  </body>
</html>
"""


def _num(v: float) -> float:
    return round(float(v), 3)


def index_html(layout: dict, camera: list[dict], cursor: list[dict], clicks: list[dict], out_w: int, out_h: int,
               duration: float, background: tuple[str, str] = ("#151412", "#3A3326"), pointer: str = "arrow",
               cursor_scale: float = 1.6, video: str = "assets/raw.mp4") -> str:
    if pointer not in POINTERS:
        raise ValueError(f"pointer must be arrow or finger, not {pointer!r}")
    cam = [{"t": _num(k["t"]), "scale": _num(k["scale"]), "cx": _num(k["cx"]), "cy": _num(k["cy"])} for k in camera]
    cur = [{"t": _num(k["t"]), "from": _num(k.get("from", k["t"])), "x": _num(k["x"]), "y": _num(k["y"]),
            "hand": bool(k.get("hand"))} for k in cursor]
    clk = [{"t": _num(k["t"]), "x": _num(k["x"]), "y": _num(k["y"])} for k in clicks]
    lay = {k: _num(layout[k]) for k in ("x", "y", "w", "h")}
    lay["scale"] = round(float(layout["scale"]), 6)
    cursor_px = round(24 * cursor_scale * lay["scale"], 2)
    ripples = "\n".join(f'        <div class="ripple" id="ripple-{i}"></div>' for i in range(len(clk)))
    subs = {
        "__W__": str(out_w), "__H__": str(out_h), "__DUR__": str(round(float(duration), 3)),
        "__BG_A__": background[0], "__BG_B__": background[1],
        "__SX__": str(lay["x"]), "__SY__": str(lay["y"]), "__SW__": str(lay["w"]), "__SH__": str(lay["h"]),
        "__R__": str(layout.get("radius", 18)), "__CS__": str(cursor_px), "__VIDEO__": video,
        "__RIPPLES__": ripples, "__ARROW__": ARROW_SVG + HAND_SVG if pointer == "arrow" else "",
        "__CURSOR_STYLE__": "" if pointer == "arrow" else ' style="display:none"',
        "__CAM__": json.dumps(cam or [{"t": 0, "scale": 1, "cx": 0, "cy": 0}]), "__CUR__": json.dumps(cur),
        "__CLK__": json.dumps(clk), "__L__": json.dumps(lay), "__POINTER__": pointer,
    }
    page = PAGE
    for key, value in subs.items():
        page = page.replace(key, value)
    return page
