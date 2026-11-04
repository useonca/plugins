"""The thin shell: subprocess calls to ffmpeg, ffprobe, parakeet-mlx and scenedetect.

No decisions here; core.py makes them. Every command is printed before it runs
so a log shows exactly what happened. Tools and Node 22+ are found by the
video-render skill's doctor.py (its sibling folder in this plugin), so the two
skills agree on where they look.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "video-render" / "scripts"))
import doctor  # noqa: E402


def find_tool(name: str, path_env: str | None = None, home: Path | None = None) -> str | None:
    """``name`` on PATH, else in ``~/.local/bin`` (where ``uv tool install`` puts it); None when missing."""
    return doctor.find_tool(name, path_env, home)


def find_node22(path_env: str | None = None, home: Path | None = None, **kwargs) -> str | None:
    """A Node 22+ binary (PATH, Homebrew's node@22 or later, nvm's newest v22 or later), or None."""
    return doctor.find_node22(path_env, home, **kwargs)


def tool(name: str) -> str:
    """The path of ``name``, or stop with its install command (run `python3 doctor.py check` for all of them)."""
    found = find_tool(name)
    if not found:
        raise SystemExit(f"{name} not found: install it with `{doctor.INSTALL[name]}` (after the founder's yes)")
    return found


def log(msg: str) -> None:
    print(f"[video-edit] {msg}", file=sys.stderr, flush=True)


def run(cmd: list[str], *, env: dict | None = None, check: bool = True, quiet: bool = True) -> subprocess.CompletedProcess:
    log("$ " + " ".join(_q(c) for c in cmd))
    p = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, **(env or {})})
    if check and p.returncode != 0:
        sys.stderr.write(p.stderr[-4000:])
        raise SystemExit(f"command failed ({p.returncode}): {cmd[0]}")
    if not quiet:
        sys.stderr.write(p.stderr)
    return p


def _q(s: str) -> str:
    return s if s and all(c.isalnum() or c in "-_./=:,+" for c in s) else "'" + s.replace("'", "'\\''") + "'"


def probe(path: str | Path) -> dict:
    p = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)])
    d = json.loads(p.stdout)
    v = next((s for s in d["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in d["streams"] if s["codec_type"] == "audio"), None)
    fps = 30.0
    if v and v.get("avg_frame_rate", "0/0") != "0/0":
        n, m = v["avg_frame_rate"].split("/")
        fps = round(int(n) / int(m), 3)
    return {
        "path": str(Path(path).resolve()),
        "duration": round(float(d["format"]["duration"]), 3),
        "width": v and v["width"],
        "height": v and v["height"],
        "fps": fps,
        "has_audio": a is not None,
        "audio_rate": a and int(a.get("sample_rate", 0)),
    }


def ffmpeg_log(args: list[str]) -> str:
    """Run an analysis pass (`-f null -`) and return its stderr."""
    return run(["ffmpeg", "-hide_banner", "-nostats", *args, "-f", "null", "-"]).stderr


def extract_wav(src: str | Path, dst: str | Path, rate: int = 16000) -> None:
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-vn", "-ac", "1", "-ar", str(rate), str(dst)])


def parakeet_json(wav: str | Path, out_dir: str | Path) -> dict:
    """Word-timed transcript. Offline first: the model is cached and the hub check alone can take minutes."""
    out_dir = Path(out_dir)
    args = [tool("parakeet-mlx"), str(wav), "--output-format", "json", "--output-dir", str(out_dir)]
    p = run(args, env={"HF_HUB_OFFLINE": "1"}, check=False)
    if p.returncode != 0:
        log("offline transcription failed (model not cached yet?), retrying online")
        run(args)
    return json.loads((out_dir / (Path(wav).stem + ".json")).read_text())


def frame_png(src: str | Path, t: float, dst: str | Path, width: int = 270) -> None:
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{t:.3f}", "-i", str(src), "-frames:v", "1", "-vf", f"scale={width}:-2", str(dst)])


def contact_sheet(src: str | Path, times: list[float], dst: str | Path, cols: int = 7, width: int = 270) -> None:
    """Frames at `times` tiled cols wide into one PNG (no drawtext here, so the order is the label)."""
    tmp = Path(dst).with_suffix("")
    tmp = tmp.parent / (tmp.name + "-frames")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    for k, t in enumerate(times):
        frame_png(src, t, tmp / f"f{k:03d}.png", width)
    rows = -(-len(times) // cols)
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-framerate", "1", "-i", str(tmp / "f%03d.png"),
         "-vf", f"tile={cols}x{rows}:padding=6:margin=6:color=0x202020", "-frames:v", "1", str(dst)])


def scenes(src: str | Path, out_dir: str | Path) -> list[dict]:
    """Shot list from PySceneDetect (adaptive detector)."""
    out_dir = Path(out_dir)
    run([tool("scenedetect"), "-q", "-i", str(src), "-o", str(out_dir), "detect-adaptive", "list-scenes", "-f", "scenes.csv"], check=False)
    csv = out_dir / "scenes.csv"
    if not csv.exists():
        return []
    rows = [line.split(",") for line in csv.read_text().splitlines()]
    head = next((k for k, r in enumerate(rows) if r and r[0] == "Scene Number"), None)
    if head is None:
        return []
    cols = rows[head]
    si, ei = cols.index("Start Time (seconds)"), cols.index("End Time (seconds)")
    return [{"start": float(r[si]), "end": float(r[ei])} for r in rows[head + 1:] if len(r) > ei]
