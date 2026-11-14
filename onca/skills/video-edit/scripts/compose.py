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
# The caption font, Montserrat Black (OFL), from Google Fonts; never a system fallback.
FONT_LINK = '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Montserrat:wght@900&display=block">'
FONT_CHECK = '900 60px "Montserrat"'
CHAR_EM = 0.66  # rough average glyph width of Montserrat Black, in em


def layout_for(width: int, height: int) -> dict:
    """The caption band for a frame: the style for its shape (set for 1080x1920 and 1920x1080), scaled to it."""
    base = STYLES["portrait" if height > width else "landscape"]
    sx, sy = (width / 1080, height / 1920) if height > width else (width / 1920, height / 1080)
    return {"left": round(base["left"] * sx), "width": round(base["width"] * sx), "top": round(base["top"] * sy),
            "height": round(base["height"] * sy), "max_px": base["max_px"] * min(sx, sy), "min_px": base["min_px"] * min(sx, sy)}


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


def caption_look(scrim: bool = True) -> str:
    """The declarations of a caption line (`.cap-in`), shared by the scene and the caption cards."""
    return ('font-family: "Montserrat"; font-weight: 900; line-height: 1.12; color: #FFFFFF; letter-spacing: -0.01em; '
            "text-wrap: balance; -webkit-text-stroke: 0.1em #111111; paint-order: stroke fill; "
            "text-shadow: 0 0.06em 0.18em rgba(0,0,0,0.55); " + (SCRIM if scrim else ""))


def captions_html(groups: list[dict], width: int, height: int, duration: float, accent: str = "#FFC93C",
                  band: dict | None = None, scrim: bool = True) -> str:
    """The captions scene. The scrim (a dark box sized to the text) keeps captions
    readable over busy footage or text already in the picture."""
    band = band or layout_for(width, height)
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
    .cap-in {{ {caption_look(scrim)} }}
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
    {FONT_LINK}
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



def caption_card_html(group: dict, lit: int, band: dict, accent: str, font_px: int) -> str:
    """One caption state as a page the band's size with a transparent body: drawn once to a
    PNG and laid over the video by ffmpeg. The look is captions_html's, word `lit` in the accent colour."""
    lit_style = f' style="color:{accent}"'
    spans = " ".join(f'<span class="w"{lit_style if k == lit else ""}>{html.escape(w["text"])}</span>'
                     for k, w in enumerate(group["words"]))
    return f"""<!doctype html>
<html><head><meta charset="UTF-8">{FONT_LINK}
<style>
  html, body {{ margin: 0; padding: 0; width: {band['width']}px; height: {band['height']}px; background: transparent; overflow: hidden; }}
  .cap {{ width: {band['width']}px; height: {band['height']}px; display: flex; align-items: center; justify-content: center; text-align: center; }}
  .cap-in {{ {caption_look()} font-size: {font_px}px; }}
  .w {{ color: #FFFFFF; }}
</style></head>
<body><div class="cap"><div class="cap-in">{spans}</div></div></body></html>
"""
