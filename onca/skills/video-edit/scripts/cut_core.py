"""Pure decisions for the smart cut: copy the picture between keyframes, re-encode only the edges.

A kept range [s, e] is copied from the first keyframe at or after s to the last at or before e when that stretch
is at least min_copy long; the bits before and after are re-encoded to match the source, so the pieces join
into one stream. cut.py runs ffmpeg and checks the result with check_cut; a miss falls back to a full encode.
"""

from __future__ import annotations

import core

EPS = 1e-3

# Edge encoders per source codec; the edges are short, so quality wins over speed. No B-frames: every edge frame
# keeps its own timestamp order, so the joined stream never reorders across a join.
EDGE_ENCODERS = {
    ("h264", "x264"): ["-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-bf", "0"],
    ("h264", "videotoolbox"): ["-c:v", "h264_videotoolbox", "-q:v", "75"],
    ("hevc", "x264"): ["-c:v", "libx265", "-preset", "veryfast", "-crf", "18", "-bf", "0"],
    ("hevc", "videotoolbox"): ["-c:v", "hevc_videotoolbox", "-q:v", "75", "-tag:v", "hvc1"],
}


def plan_pieces(ranges: list[dict], keyframes: list[float], fps: float, min_copy: float = 2.0) -> list[dict]:
    """Per kept range, in order: [{"start", "end", "mode": "copy"|"encode", "range": k}], edges on frames."""
    out = []
    for k, r in enumerate(ranges):
        s, e = core.snap(r["start"], fps), core.snap(r["end"], fps)
        k1 = next((t for t in keyframes if t >= s - EPS), None)
        k2 = next((t for t in reversed(keyframes) if t <= e + EPS), None)
        if k1 is not None and k2 is not None and k2 - k1 >= min_copy - EPS:
            k1, k2 = core.snap(k1, fps), core.snap(k2, fps)
            parts = [(s, k1, "encode"), (k1, k2, "copy"), (k2, e, "encode")]
        else:
            parts = [(s, e, "encode")]
        for a, b, mode in parts:
            if b - a >= 0.5 / fps:
                out.append({"start": a, "end": b, "mode": mode, "range": k})
    return out


def expected_frames(pieces: list[dict], fps: float) -> int:
    """The frame count the joined pieces should decode to."""
    return sum(round((p["end"] - p["start"]) * fps) for p in pieces)


def _num(t: float) -> str:
    return repr(round(t, 4))


def _profile(codec: str, profile: str | None) -> str | None:
    p = (profile or "").lower().replace(" ", "")
    if not p:
        return None
    if "baseline" in p:
        return "baseline"
    return {"high10": "high10", "main10": "main10"}.get(p, p)


def encode_args(probe: dict, piece: dict, encoder: str) -> list[str]:
    """ffmpeg args (without the output path) for one re-encoded piece that matches the source stream.
    ValueError for a codec it cannot match (not h264 or hevc) or an encoder that is not x264 or videotoolbox."""
    codec = probe.get("codec")
    if codec not in ("h264", "hevc"):
        raise ValueError(f"smart cut matches only h264 and hevc sources, not {codec}")
    if encoder not in ("x264", "videotoolbox"):
        raise ValueError(f"unknown edge encoder {encoder}: use x264 or videotoolbox")
    fps = float(probe["fps"])
    frames = round((piece["end"] - piece["start"]) * fps)
    # A quarter frame early, so the seek keeps the frame at `start` and none before it; then exactly its frames.
    args = ["-ss", _num(max(0.0, piece["start"] - 0.25 / fps)), "-i", probe["path"], "-frames:v", str(frames),
            *EDGE_ENCODERS[(codec, encoder)]]
    profile = _profile(codec, probe.get("profile"))
    if profile:
        args += ["-profile:v", profile]
    for key, flag in (("color_primaries", "-color_primaries"), ("color_transfer", "-color_trc"), ("color_space", "-colorspace")):
        if probe.get(key):  # an edge tagged like the copied stretch beside it (no colour flash at an HDR cut)
            args += [flag, probe[key]]
    args += ["-pix_fmt", probe.get("pix_fmt") or "yuv420p", "-fps_mode", "passthrough", "-an", "-f", "mpegts"]
    return args


def copy_args(piece: dict, src: str, fps: float) -> list[str]:
    """ffmpeg args for one copied piece: the seek lands just past its keyframe, so that keyframe opens it, and
    it keeps exactly the frames up to the next piece's keyframe (packets in decode order: whole closed GOPs)."""
    return ["-ss", _num(piece["start"] + 0.001), "-i", src, "-frames:v", str(round((piece["end"] - piece["start"]) * fps)),
            "-c:v", "copy", "-an", "-f", "mpegts"]


def concat_list(paths: list[str], durations: list[float] | None = None) -> str:
    """The concat demuxer's list, single quotes escaped the way it reads them; with `durations`, each file
    lasts exactly that long on the joined timeline."""
    out = []
    for k, p in enumerate(paths):
        out.append("file '" + str(p).replace("'", "'\\''") + "'\n")
        if durations:
            out.append(f"duration {_num(durations[k])}\n")
    return "".join(out)


def join_windows(pieces: list[dict], fps: float, pad: float = 1.0) -> list[tuple]:
    """Output-time windows around every join between pieces (`pad` s each side), merged: what the check decodes.
    The copied stretches between them are the source's own packets, unchanged."""
    out, t = [], 0.0
    for p in pieces[:-1]:
        t += round((p["end"] - p["start"]) * fps) / fps
        a, b = max(0.0, t - pad), t + pad
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], b)
        else:
            out.append((a, b))
    return [(round(a, 3), round(b, 3)) for a, b in out]


def check_cut(expected_frames: int, got_frames: int, expected_dur: float, got_dur: float, decode_errors: str,
              fps: float) -> list[str]:
    """Problems with a smart cut's output; empty means it can ship."""
    problems = []
    if abs(got_frames - expected_frames) > 1:
        problems.append(f"frames: decoded {got_frames}, planned {expected_frames}")
    if abs(got_dur - expected_dur) > 1 / fps + 0.02:
        problems.append(f"duration: {got_dur:.3f} s, planned {expected_dur:.3f} s")
    errors = [ln for ln in decode_errors.splitlines() if ln.strip()]
    if errors:
        problems.append(f"decode errors ({len(errors)}): {errors[0][:200]}")
    return problems
