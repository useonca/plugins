"""The founder cut out of their own talking clip: which route runs here (the render engine's free cut-out on every
computer, Apple Vision on a Mac when asked), the exact commands, and the presenter's places on the frame. Pure:
kit.py runs the commands."""

from __future__ import annotations

from pathlib import Path

DEFAULT_ROUTE = "engine"
ROUTES = ("engine", "vision")
VISION_MIN_MAC = 12  # VNGeneratePersonSegmentationRequest
PRESENTER_SWIFT = Path(__file__).resolve().parent / "presenter.swift"
ENGINE_QUALITY = "best"
VISION_QUALITIES = ("accurate", "balanced")
# The WebM the page plays: VP9 with an alpha channel (the engine reads it).
VP9_ALPHA = ("-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-auto-alt-ref", "0", "-b:v", "0", "-crf", "30")

# The presenter's boxes on a 1080 x 1920 frame (the cut-out fills its box, cover, anchored at its bottom).
FRAME = (1080, 1920)
PLACEMENTS = {"bottom": {"x": 0, "y": 1080, "w": 1080, "h": 840},
              "full": {"x": 0, "y": 0, "w": 1080, "h": 1920},
              "corner": {"x": 680, "y": 1400, "w": 360, "h": 420}}


def route(asked, platform: str, mac_major: int, has_swift: bool) -> str:
    """The cut-out route: the engine unless Vision is asked for; Vision only where it can run."""
    if asked in (None, "", "engine"):
        return "engine"
    if asked != "vision":
        raise ValueError(f"unknown cut-out route {asked!r} (engine or vision)")
    if platform != "darwin" or mac_major < VISION_MIN_MAC:
        raise ValueError(f"Apple Vision needs macOS {VISION_MIN_MAC} or newer; use the engine route (the default)")
    if not has_swift:
        raise ValueError("Apple Vision needs swift (xcode-select --install); or use the engine route (the default)")
    return "vision"


def commands(route_name: str, clip, work, out_webm, swift, engine_cmd: list, ffmpeg: str, quality: str = "balanced",
             fps: float = 30) -> list:
    """The argv steps that turn the clip into a transparent WebM: Vision's frames then the VP9 encode, or the
    engine's remove-background."""
    if route_name == "engine":
        return [[*map(str, engine_cmd), "remove-background", str(clip), "-o", str(out_webm), "--quality", ENGINE_QUALITY]]
    if route_name == "vision":
        if quality not in VISION_QUALITIES:
            raise ValueError(f"quality must be accurate or balanced, got {quality!r}")
        return [[str(swift), str(PRESENTER_SWIFT), str(clip), str(work), "--quality", quality],
                [str(ffmpeg), "-v", "error", "-y", "-framerate", f"{fps:g}", "-i", str(Path(work) / "f%06d.png"),
                 *VP9_ALPHA, str(out_webm)]]
    raise ValueError(f"unknown cut-out route {route_name!r}")


def audio_command(ffmpeg: str, clip, wav) -> list:
    """The clip's voice as 48 kHz mono 16-bit PCM."""
    return [str(ffmpeg), "-v", "error", "-y", "-i", str(clip), "-vn", "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le", str(wav)]


def placement(name: str, size: list) -> dict:
    """{x, y, w, h} of a presenter place on a frame of `size`, scaled per axis from 1080 x 1920."""
    if name not in PLACEMENTS:
        raise ValueError(f"unknown presenter place {name!r} (one of {', '.join(PLACEMENTS)})")
    sx, sy = size[0] / FRAME[0], size[1] / FRAME[1]
    box = PLACEMENTS[name]
    return {"x": round(box["x"] * sx), "y": round(box["y"] * sy), "w": round(box["w"] * sx), "h": round(box["h"] * sy)}


def clip_words(words: list) -> list:
    """The transcript's words as words.json from kit.py voice: each with its line (`clip`)."""
    return [{"text": w["text"], "start": w["start"], "end": w["end"], "line": "clip"}
            for w in words if isinstance(w, dict) and str(w.get("text", "")).strip()]


def presenter_tag() -> str:
    """The cut-out's element: above the scenes, and kept out of the engine's motion blur (a blurred slide or whip
    is drawn on a layer of its own, which would cover the founder)."""
    return ('<video id="presenter" class="clip om-presenter" src="presenter.webm" data-start="0" data-track-index="2" '
            'muted playsinline data-motion-blur="off" data-layout-allow-occlusion></video>')
