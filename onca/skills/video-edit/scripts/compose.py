"""Pure HTML for the HyperFrames caption project (no files, no subprocesses).

One root composition: the cut video (muted; its sound is muxed back after the
render) and one captions sub-composition holding every phrase as its own clip.
"""

from __future__ import annotations

import html
import json

STYLES = {
    # canvas -> caption band. Portrait stays inside TikTok's safe zone (x 120-940, y 220-1440) and Instagram's feed crop (y 285-1635): y 285-1440.
    "portrait": {"left": 120, "width": 820, "top": 1150, "height": 270, "max_px": 92, "min_px": 58},
    "landscape": {"left": 160, "width": 1600, "top": 850, "height": 150, "max_px": 84, "min_px": 52},
}
CHAR_EM = 0.66  # rough average glyph width of Montserrat Black, in em


def layout_for(width: int, height: int) -> dict:
    return STYLES["portrait" if height > width else "landscape"]


def font_px(text: str, band: dict) -> int:
    """Largest size that fits the text on one line of the band; when even the band's
    minimum is too big for one line, the size that fits it on two lines."""
    one = band["width"] / max(1, len(text)) / CHAR_EM
    if one >= band["min_px"]:
        return int(min(band["max_px"], one))
    two = 2 * band["width"] / max(1, len(text)) / CHAR_EM * 0.9
    return int(max(band["min_px"] * 0.9, min(band["max_px"] * 0.85, two)))


SCRIM = ("background: rgba(17,17,17,0.78); padding: 0.1em 0.38em; border-radius: 0.28em; "
         "-webkit-box-decoration-break: clone; box-decoration-break: clone;")


def captions_html(groups: list[dict], width: int, height: int, duration: float, accent: str = "#FFC93C",
                  band: dict | None = None, scrim: bool = True) -> str:
    """The captions scene. The scrim (a dark box sized to the text) keeps captions
    readable over busy footage or text already in the picture."""
    band = band or layout_for(width, height)
    scrim_css = SCRIM if scrim else ""
    rows, tweens = [], []
    for g, group in enumerate(groups):
        size = font_px(group["text"], band)
        spans = " ".join(f'<span id="w{g}-{k}" class="w">{html.escape(w["text"])}</span>' for k, w in enumerate(group["words"]))
        dur = round(group["end"] - group["start"], 3)
        rows.append(
            f'    <div id="cap-{g}" class="clip cap" data-start="{group["start"]}" data-duration="{dur}" data-track-index="1">\n'
            f'      <div id="cap-in-{g}" class="cap-in" style="font-size:{size}px">{spans}</div>\n'
            f"    </div>"
        )
        tweens.append(f'  tl.fromTo("#cap-in-{g}", {{opacity: 0, scale: 0.86}}, {{opacity: 1, scale: 1, duration: 0.12, ease: "power3.out"}}, {group["start"]});')
        for k, w in enumerate(group["words"]):
            tweens.append(f'  tl.set("#w{g}-{k}", {{color: "{accent}"}}, {max(w["start"], group["start"])});')
            if k < len(group["words"]) - 1:
                tweens.append(f'  tl.set("#w{g}-{k}", {{color: "#FFFFFF"}}, {group["words"][k + 1]["start"]});')
    return f"""<template>
  <style>
    #root {{ position: absolute; inset: 0; }}
    .cap {{ position: absolute; left: {band['left']}px; top: {band['top']}px; width: {band['width']}px; height: {band['height']}px;
            display: flex; align-items: center; justify-content: center; text-align: center; overflow: visible; }}
    .cap-in {{ font-family: "Montserrat", sans-serif; font-weight: 900; line-height: 1.12; color: #FFFFFF;
              -webkit-text-stroke: 0.1em #111111; paint-order: stroke fill;
              text-shadow: 0 0.06em 0.18em rgba(0,0,0,0.55);
              {scrim_css} }}
    .w {{ color: #FFFFFF; }}
  </style>
  <div id="root" data-composition-id="captions" data-width="{width}" data-height="{height}" data-duration="{duration}">
{chr(10).join(rows)}
  </div>
  <script>
  const tl = gsap.timeline({{ paused: true }});
{chr(10).join(tweens)}
  window.__timelines["captions"] = tl;
  </script>
</template>
"""


def index_html(width: int, height: int, duration: float, video: str = "assets/cut.mp4") -> str:
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
    <style>
      html, body {{ margin: 0; padding: 0; width: {width}px; height: {height}px; overflow: hidden; background: #000; }}
      #main {{ position: relative; width: {width}px; height: {height}px; overflow: hidden; }}
      #cut {{ position: absolute; left: 0; top: 0; width: {width}px; height: {height}px; object-fit: contain; z-index: 1; }}
      #captions {{ position: absolute; inset: 0; z-index: 2; }}
    </style>
  </head>
  <body>
    <div id="main" data-composition-id="main" data-start="0" data-duration="{duration}" data-width="{width}" data-height="{height}">
      <video id="cut" class="clip" src="{video}" muted playsinline data-start="0" data-duration="{duration}" data-track-index="0"></video>
      <div id="captions" data-composition-id="captions" data-composition-src="compositions/captions.html" data-track-kind="captions"
           data-start="0" data-duration="{duration}" data-track-index="1" data-width="{width}" data-height="{height}"></div>
    </div>
    <script>
      window.__timelines = window.__timelines || {{}};
      window.__timelines["main"] = gsap.timeline({{ paused: true }});
    </script>
  </body>
</html>
"""


def groups_json(groups: list[dict]) -> str:
    return json.dumps([{"text": g["text"], "start": g["start"], "end": g["end"]} for g in groups], indent=1)
