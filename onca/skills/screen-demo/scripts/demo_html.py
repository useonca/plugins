"""The long demo's root composition: each scene's footage (a muted video trimmed with `data-media-start`) or a
title card, one narration track per voiced scene, a chapter label at each chapter start and optional burned
captions. Pure: it returns the page's text. Fades come from the engine's time in an `hf-seek` listener (no
GSAP), so every frame renders on its own.
"""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from demo_core import fonts_for, no_orphan, smart_quotes  # noqa: E402

LABEL_SECONDS = 2.5


def _n(v: float) -> str:
    v = round(float(v), 3)
    return str(int(v)) if v == int(v) else str(v)


def _card_parts(card) -> tuple[str, str]:
    if isinstance(card, dict):
        return str(card.get("title", "")), str(card.get("text", ""))
    return str(card or ""), ""


def font_link(fonts: dict) -> str:
    """The Google Fonts stylesheet for the display and text families (weights 400 to 800)."""
    fams = []
    for name in dict.fromkeys([fonts["display"], fonts["text"]]):
        fams.append("family=" + name.replace(" ", "+") + ":wght@400;500;600;700;800")
    return f'<link rel="stylesheet" href="https://fonts.googleapis.com/css2?{"&".join(fams)}&display=block">'


def index_html(tl: list[dict], marks: list[dict], w: int, h: int, duration: float,
               captions: list[dict] | None = None, fonts: dict | None = None) -> str:
    fonts = fonts or fonts_for({})
    rows = []
    fades = []
    for s in tl:
        length = s["end"] - s["start"]
        sid = html.escape(s["id"])
        if s.get("clip"):
            rows.append(
                f'      <video id="v-{sid}" class="clip scene" src="{html.escape(s["clip"])}" muted playsinline '
                f'data-start="{_n(s["start"])}" data-duration="{_n(length)}" data-media-start="{_n(s.get("clip_from") or 0)}" '
                f'data-track-index="0" style="z-index: 1"></video>')
        else:
            title, text = _card_parts(s.get("card"))
            sub = f'<p class="card-text">{html.escape(no_orphan(smart_quotes(text)))}</p>' if text else ""
            rows.append(
                f'      <div id="c-{sid}" class="clip card" data-start="{_n(s["start"])}" data-duration="{_n(length)}" '
                f'data-track-index="0" style="z-index: 1"><div class="card-in" id="ci-{sid}">'
                f'<h1 class="card-title">{html.escape(no_orphan(smart_quotes(title)))}</h1>{sub}</div></div>')
            fades.append({"id": f"ci-{s['id']}", "t": s["start"], "kind": "card"})
        if s.get("audio") and s.get("voice_start") is not None:
            rows.append(
                f'      <audio id="a-{sid}" class="clip" src="{html.escape(s["audio"])}" data-start="{_n(s["voice_start"])}" '
                f'data-duration="{_n(s["voice_end"] - s["voice_start"])}" data-volume="1" data-track-index="2"></audio>')
    for k, m in enumerate(marks):
        rows.append(
            f'      <div id="ch-{k}" class="clip chapter" data-start="{_n(m["t"])}" data-duration="{_n(min(LABEL_SECONDS, duration - m["t"]))}" '
            f'data-track-index="3" style="z-index: 3"><span class="chapter-n">{k + 1:02d}</span>'
            f'<span class="chapter-title">{html.escape(m["title"])}</span></div>')
        fades.append({"id": f"ch-{k}", "t": m["t"], "kind": "label"})
    for k, c in enumerate(captions or []):
        text = "<br>".join(html.escape(line) for line in c["text"].split("\n"))
        rows.append(
            f'      <div id="cap-{k}" class="clip caption" data-start="{_n(c["start"])}" data-duration="{_n(c["end"] - c["start"])}" '
            f'data-track-index="4" style="z-index: 4"><span>{text}</span></div>')
    body = "\n".join(rows)
    unit = h / 1080
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    {font_link(fonts)}
    <style>
      html, body {{ margin: 0; padding: 0; width: {w}px; height: {h}px; overflow: hidden; background: #151412; }}
      #main {{ position: relative; width: {w}px; height: {h}px; overflow: hidden; font-family: "{fonts['text']}";
               -webkit-font-smoothing: antialiased; font-optical-sizing: auto; font-kerning: normal; }}
      .scene {{ position: absolute; left: 0; top: 0; width: {w}px; height: {h}px; object-fit: contain; background: #151412; }}
      .card {{ position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
               background: linear-gradient(135deg, #151412 0%, #3A3326 100%); color: #fff; text-align: center; }}
      .card-in {{ max-width: {round(w * 0.7)}px; }}
      .card-title {{ margin: 0; font-family: "{fonts['display']}"; font-size: {round(76 * unit)}px; font-weight: 700;
                     line-height: 1.08; letter-spacing: -0.022em; text-wrap: balance; }}
      .card-text {{ margin: {round(24 * unit)}px auto 0; max-width: 28em; font-size: {round(34 * unit)}px; font-weight: 400;
                    color: rgba(255,255,255,.72); line-height: 1.35; letter-spacing: -0.005em; text-wrap: pretty; }}
      .chapter {{ position: absolute; left: {round(64 * unit)}px; top: {round(56 * unit)}px; display: flex; gap: {round(16 * unit)}px;
                  align-items: baseline; padding: {round(14 * unit)}px {round(24 * unit)}px; border-radius: {round(14 * unit)}px;
                  background: rgba(21,20,18,.78); color: #fff; }}
      .chapter-n {{ font-size: {round(24 * unit)}px; font-weight: 700; color: #F2B53A; }}
      .chapter-title {{ font-family: "{fonts['display']}"; font-size: {round(34 * unit)}px; font-weight: 700; letter-spacing: -0.012em; }}
      .caption {{ position: absolute; left: 0; right: 0; bottom: {round(72 * unit)}px; text-align: center; }}
      .caption span {{ display: inline-block; padding: {round(10 * unit)}px {round(22 * unit)}px; border-radius: {round(10 * unit)}px;
                       background: rgba(0,0,0,.72); color: #fff; font-size: {round(40 * unit)}px; font-weight: 600; line-height: 1.3;
                       letter-spacing: -0.008em; text-wrap: balance; }}
    </style>
  </head>
  <body>
    <div id="main" data-composition-id="main" data-start="0" data-duration="{_n(duration)}" data-width="{w}" data-height="{h}" data-no-timeline>
{body}
    </div>
    <script>
      (() => {{
        const FADES = {json.dumps(fades)};
        const LABEL = {LABEL_SECONDS};
        const out = (p) => 1 - Math.pow(1 - Math.min(1, Math.max(0, p)), 3);
        const els = FADES.map((f) => [f, document.getElementById(f.id)]);
        function renderAt(t) {{
          for (const [f, el] of els) {{
            if (!el) continue;
            const p = out((t - f.t) / 0.35);
            let o = p;
            if (f.kind === "label") o = Math.min(p, out((f.t + LABEL - t) / 0.25));
            el.style.opacity = String(o);
            el.style.filter = f.kind === "card" ? `blur(${{(1 - p) * 8}}px)` : "none";
          }}
        }}
        window.addEventListener("hf-seek", (e) => renderAt(e.detail.time));
        renderAt(0);
      }})();
    </script>
  </body>
</html>
"""
