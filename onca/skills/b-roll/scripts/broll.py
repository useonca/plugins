#!/usr/bin/env python3
"""Turn one still photo into a b-roll clip, free and local: Onca's parallax (a depth map plus Onca's own
shader in the render engine) or a pan and zoom (ffmpeg only, the fallback).

usage: broll.py photo IMG --out CLIP.mp4 [--seconds 5] [--move dolly] [--size 1920x1080]
                [--engine parallax|kenburns] [--depth DEPTH.png]

Parallax moves: dolly, orbit, pan-left, pan-right. Pan and zoom moves: in, out, left, right (a parallax move
name is mapped: dolly and orbit to in, pan-left to left, pan-right to right). The depth map comes from
depth_map.py through `uv` (a one-time download of free tools, about 800 MB, asked once); --depth reuses one.
Product UI never goes through this: it stays flat.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "screen-demo" / "scripts"))
import shared  # noqa: E402

KENBURNS_MOVES = ("in", "out", "left", "right")
PARALLAX_MOVES = ("dolly", "orbit", "pan-left", "pan-right")
TO_KENBURNS = {"dolly": "in", "orbit": "in", "pan-left": "left", "pan-right": "right"}
DEPTH_TOOLS = ("torch==2.15.0", "transformers==5.22.2", "pillow==13.0.0")


def _ease(p: float) -> float:
    return (1 - math.cos(math.pi * p)) / 2


def kenburns_filter(src_w: int, src_h: int, out_w: int, out_h: int, seconds: float, fps: int = 30,
                    move: str = "in", focus: tuple[float, float] = (0.5, 0.5)) -> str:
    """An ffmpeg filter for a cosine-eased pan and zoom: the photo is upscaled 4x (smooth sub-pixel moves),
    zoomed 1.0 to 1.12 (`in`), 1.12 to 1.0 (`out`), or held at 1.08 with a 6% drift (`left`, `right`)."""
    if move not in KENBURNS_MOVES:
        raise ValueError(f"move must be one of {', '.join(KENBURNS_MOVES)}, not {move!r}")
    if seconds <= 0:
        raise ValueError("seconds must be more than 0")
    n = max(1, round(seconds * fps))
    big_w, big_h = out_w * 4, out_h * 4
    p = f"((1-cos(PI*on/{max(1, n - 1)}))/2)"
    fx, fy = focus
    zoom = {"in": f"1+0.12*{p}", "out": f"1.12-0.12*{p}"}.get(move, "1.08")
    cx = {"left": f"({fx}+0.03-0.06*{p})", "right": f"({fx}-0.03+0.06*{p})"}.get(move, f"{fx}")
    x = f"max(0,min(iw-iw/zoom,iw*{cx}-iw/zoom/2))"
    y = f"max(0,min(ih-ih/zoom,ih*{fy}-ih/zoom/2))"
    cover = (f"scale={big_w}:{big_h}:force_original_aspect_ratio=increase:flags=lanczos,"
             f"crop={big_w}:{big_h}:(iw-{big_w})*{fx}:(ih-{big_h})*{fy}")
    return f"{cover},zoompan=z='{zoom}':x='{x}':y='{y}':d={n}:s={out_w}x{out_h}:fps={fps},setsar=1"


def parallax_path(move: str, seconds: float, fps: int = 30, intensity: float = 0.03) -> list[dict]:
    """One camera point {t, ox, oy, zoom} per frame, cosine eased: `dolly` zooms 1.0 to 1.08, `orbit` circles
    once (ox = intensity * sin, oy = intensity / 2 * cos), `pan-left` / `pan-right` slide ox to -/+ intensity."""
    if move not in PARALLAX_MOVES:
        raise ValueError(f"move must be one of {', '.join(PARALLAX_MOVES)}, not {move!r}")
    if seconds <= 0:
        raise ValueError("seconds must be more than 0")
    n = max(2, round(seconds * fps))
    out = []
    for k in range(n):
        p = _ease(k / (n - 1))
        ox = oy = 0.0
        zoom = 1.0
        if move == "dolly":
            zoom = 1.0 + 0.08 * p
        elif move == "orbit":
            a = 2 * math.pi * p
            ox, oy = intensity * math.sin(a), intensity / 2 * math.cos(a)
        else:
            ox = (-1 if move == "pan-left" else 1) * intensity * p
        out.append({"t": round(k / fps, 4), "ox": round(ox, 5), "oy": round(oy, 5), "zoom": round(zoom, 5)})
    return out


PAGE = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <style>
      html, body { margin: 0; padding: 0; width: __W__px; height: __H__px; overflow: hidden; background: #000; }
      #main { position: relative; width: __W__px; height: __H__px; overflow: hidden; }
      #view { position: absolute; left: 0; top: 0; width: __W__px; height: __H__px; }
    </style>
  </head>
  <body>
    <div id="main" data-composition-id="main" data-start="0" data-duration="__DUR__" data-width="__W__" data-height="__H__"
         data-motion-blur="on" data-motion-blur-events="on" data-no-timeline>
      <canvas id="view" width="__W__" height="__H__"></canvas>
    </div>
    <script>
      (() => {
        const PATH = __PATH__;
        const FOCUS = __FOCUS__;
        const FPS = __FPS__;
        const canvas = document.getElementById("view");
        const gl = canvas.getContext("webgl", { preserveDrawingBuffer: true, antialias: false });
        const VS = "attribute vec2 a; varying vec2 uv; void main() { uv = a * 0.5 + 0.5; uv.y = 1.0 - uv.y; gl_Position = vec4(a, 0.0, 1.0); }";
        // Each pixel looks up the photo shifted by offset * (depth - focus); a short march from the nearest layer
        // to the farthest finds what a nearer pixel hides, and the clamp stretches the edges.
        const FS = `precision highp float;
          uniform sampler2D img; uniform sampler2D dep; uniform vec2 off; uniform float zoom; uniform float focus; uniform vec2 fit;
          varying vec2 uv;
          void main() {
            vec2 p = (uv - 0.5) * fit / (zoom * 1.06) + 0.5;
            vec2 q = p;
            for (int i = 0; i < 32; i++) {
              float d = 1.0 - float(i) / 31.0;
              vec2 c = clamp(p - off * (d - focus), 0.0, 1.0);
              if (texture2D(dep, c).r >= d - 0.02) { q = c; break; }
              q = c;
            }
            gl_FragColor = texture2D(img, clamp(q, 0.0, 1.0));
          }`;
        const shader = (type, src) => { const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s); return s; };
        const prog = gl.createProgram();
        gl.attachShader(prog, shader(gl.VERTEX_SHADER, VS));
        gl.attachShader(prog, shader(gl.FRAGMENT_SHADER, FS));
        gl.linkProgram(prog);
        gl.useProgram(prog);
        const buf = gl.createBuffer();
        gl.bindBuffer(gl.ARRAY_BUFFER, buf);
        gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
        const loc = gl.getAttribLocation(prog, "a");
        gl.enableVertexAttribArray(loc);
        gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
        const U = {};
        for (const n of ["img", "dep", "off", "zoom", "focus", "fit"]) U[n] = gl.getUniformLocation(prog, n);
        const load = (src) => new Promise((ok, fail) => { const im = new Image(); im.onload = () => ok(im); im.onerror = fail; im.src = src; });
        const texture = (unit, im) => {
          const t = gl.createTexture();
          gl.activeTexture(gl.TEXTURE0 + unit);
          gl.bindTexture(gl.TEXTURE_2D, t);
          gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
          gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
          gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
          gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
          gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, im);
        };
        let ready = false;
        const built = Promise.all([load("__IMAGE__"), load("__DEPTH__")]).then(([im, dm]) => {
          texture(0, im);
          texture(1, dm);
          gl.uniform1i(U.img, 0);
          gl.uniform1i(U.dep, 1);
          gl.uniform1f(U.focus, FOCUS);
          const a = im.naturalWidth / im.naturalHeight, b = canvas.width / canvas.height;
          gl.uniform2f(U.fit, a > b ? b / a : 1, a > b ? 1 : a / b);
          ready = true;
        });
        window.__hf = window.__hf || {};
        window.__hf.buildReady = window.__hf.buildReady || {};
        window.__hf.buildReady["onca-parallax"] = built;
        function at(t) {
          const f = Math.min(PATH.length - 1, Math.max(0, t * FPS));
          const i = Math.floor(f), j = Math.min(PATH.length - 1, i + 1), k = f - i;
          const m = (key) => PATH[i][key] + (PATH[j][key] - PATH[i][key]) * k;
          return { ox: m("ox"), oy: m("oy"), zoom: m("zoom") };
        }
        function draw(t) {
          if (!ready) return;
          const c = at(t);
          gl.viewport(0, 0, canvas.width, canvas.height);
          gl.uniform2f(U.off, c.ox, c.oy);
          gl.uniform1f(U.zoom, c.zoom);
          gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
        }
        window.addEventListener("hf-seek", (e) => {
          if (ready) draw(e.detail.time);
          else e.detail.waitUntil(built.then(() => draw(e.detail.time)));
        });
        built.then(() => draw(0));
      })();
    </script>
  </body>
</html>
"""


def parallax_html(w: int, h: int, seconds: float, path: list[dict], image: str = "assets/photo.jpg",
                  depth: str = "assets/depth.png", focus: float = 0.5, fps: int = 30) -> str:
    """The root composition: a full-frame WebGL canvas drawn from the engine's time (no GSAP); `fps` is the
    one `path` was made with."""
    subs = {"__W__": str(w), "__H__": str(h), "__DUR__": str(round(seconds, 3)), "__PATH__": json.dumps(path),
            "__FOCUS__": str(focus), "__FPS__": str(fps), "__IMAGE__": image, "__DEPTH__": depth}
    page = PAGE
    for key, value in subs.items():
        page = page.replace(key, value)
    return page


def depth_command(script: str, image: str, out: str) -> list[str]:
    """The pinned `uv run` line for depth_map.py (Python 3.12 and its free tools, cached by uv)."""
    cmd = ["uv", "run", "--python", "3.12"]
    for tool in DEPTH_TOOLS:
        cmd += ["--with", tool]
    return cmd + ["python", script, image, "--out", out]


def photo_stamp(img: Path) -> str:
    """What a default depth map was made from (the photo's path, size and time), so it is reused only for it."""
    st = img.stat()
    return f"{img.resolve()}:{st.st_size}:{st.st_mtime_ns}"


def image_size(path: Path) -> tuple[int, int]:
    p = shared.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                    "-of", "json", str(path)])
    s = json.loads(p.stdout)["streams"][0]
    return int(s["width"]), int(s["height"])


def photo(a) -> None:
    img = Path(a.img)
    if not img.exists():
        shared.bad_input([f"no photo at {img}"])
    if a.seconds <= 0:
        shared.bad_input(["--seconds must be more than 0"])
    w, h = shared.parse_size(a.size)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if a.engine == "kenburns":
        move = TO_KENBURNS.get(a.move, a.move)
        try:
            vf = kenburns_filter(*image_size(img), w, h, a.seconds, move=move)
        except ValueError as e:
            shared.bad_input([str(e)])
        shared.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(img), "-vf", f"{vf},scale=out_range=tv,format=yuv420p",
                    "-frames:v", str(round(a.seconds * 30)), *shared.VIDEO, "-an", "-movflags", "+faststart", str(out)])
    else:
        try:
            path = parallax_path(a.move, a.seconds)
        except ValueError as e:
            shared.bad_input([str(e)])
        depth = Path(a.depth) if a.depth else out.with_name(out.stem + "-depth.png")
        stamp = depth.with_name(depth.name + ".source")
        source = photo_stamp(img)
        if not a.depth and depth.exists() and stamp.exists() and stamp.read_text(encoding="utf-8") == source:
            shared.log(f"reusing the depth map {depth} (made from this photo)")
        elif not a.depth:
            uv = shared.shell.find_tool("uv")
            if not uv:
                print("uv not found: install it with the founder's yes, or use --engine kenburns", file=sys.stderr)
                raise SystemExit(1)
            cmd = depth_command(str(HERE / "depth_map.py"), str(img), str(depth))
            shared.run([uv, *cmd[1:]])
            stamp.write_text(source, encoding="utf-8")
        elif not depth.exists():
            shared.bad_input([f"no depth map at {depth}"])
        proj = out.with_name(out.stem + "-hf")
        (proj / "assets").mkdir(parents=True, exist_ok=True)
        photo_name = "assets/photo" + img.suffix.lower()
        shutil.copyfile(img, proj / photo_name)
        shutil.copyfile(depth, proj / "assets" / "depth.png")
        (proj / "index.html").write_text(parallax_html(w, h, a.seconds, path, image=photo_name), encoding="utf-8")
        raw = proj / "render.mp4"
        shared.render(proj, raw, a.draft)
        shared.finish(raw, out, sound=False)
    sheet = shared.contact(out, a.seconds)
    shared.log(f"-> {out} (contact sheet {sheet})")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Turn a still photo into a b-roll clip (parallax or pan and zoom).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("photo")
    p.add_argument("img")
    p.add_argument("--out", required=True)
    p.add_argument("--seconds", type=float, default=5)
    p.add_argument("--move", default="dolly")
    p.add_argument("--size", default="1920x1080")
    p.add_argument("--engine", choices=("parallax", "kenburns"), default="parallax")
    p.add_argument("--depth", help="reuse a depth map made earlier")
    p.add_argument("--draft", action="store_true")
    photo(ap.parse_args(argv))


if __name__ == "__main__":
    main()
