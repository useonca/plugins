#!/usr/bin/env python3
"""Burn big, word-timed captions onto a rendered cut through HyperFrames (free, local).

usage: captions.py EDIT_DIR/edl.json --video EDIT_DIR/cut-9x16.mp4 --out final-9x16.mp4
                   [--project DIR] [--max-words 4] [--accent '#FFC93C'] [--draft]
                   [--band-top PX --band-height PX]

This Mac's ffmpeg has no drawtext or subtitles filter, so captions are HTML
rendered by the plugin's pinned render engine (HyperFrames, Node 22+). The video is rendered muted; its own sound is
copied back afterwards, so loudness stays what render.py measured.
"""
import argparse, json, shutil, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import compose, core, shell  # noqa: E402


ENGINE = Path(__file__).resolve().parents[2] / "video-render" / "scripts" / "engine.py"


def engine_cmd() -> list[str]:
    """The pinned render engine of the video-render skill (it finds Node 22+ itself)."""
    return [sys.executable, str(ENGINE)]


def hf(project: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    cmd = [*engine_cmd(), *args]
    shell.log(f"(in {project}) $ {' '.join(cmd)}")
    p = subprocess.run(cmd, cwd=project, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and p.returncode != 0:
        sys.stderr.write(p.stdout[-3000:] + p.stderr[-3000:])
        raise SystemExit(f"render engine {args[0]} failed")
    return p


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("edl")
    ap.add_argument("--video", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--project")
    ap.add_argument("--max-words", type=int, default=4)
    ap.add_argument("--accent", default="#FFC93C")
    ap.add_argument("--draft", action="store_true")
    ap.add_argument("--band-top", type=int, help="caption band top in px; pick a calm area from the contact sheet")
    ap.add_argument("--band-height", type=int)
    ap.add_argument("--no-scrim", action="store_true", help="no dark box behind the words (only over calm, dark footage)")
    a = ap.parse_args()
    edl = json.loads(Path(a.edl).read_text(encoding="utf-8"))
    info = shell.probe(a.video)
    w, h = info["width"], info["height"]
    band = dict(compose.layout_for(w, h))
    if a.band_top is not None:
        band["top"] = a.band_top
    if a.band_height is not None:
        band["height"] = a.band_height
    if h > w and band["top"] + band["height"] > 1440 * h / 1920:
        shell.log("warning: the caption band runs below y 1440, under TikTok's buttons and description")
    if h > w and band["top"] < 285 * h / 1920:
        shell.log("warning: the caption band starts above y 285, where Instagram's home feed cuts a 9:16 video")
    max_chars = 26 if h > w else 34  # portrait may wrap to two lines
    groups = core.caption_groups(edl["words_out"], max_words=a.max_words, max_chars=max_chars)
    duration = round(info["duration"], 3)
    proj = Path(a.project or Path(a.out).with_suffix("").as_posix() + "-hf")
    (proj / "assets").mkdir(parents=True, exist_ok=True)
    (proj / "compositions").mkdir(exist_ok=True)
    shutil.copyfile(a.video, proj / "assets" / "cut.mp4")
    (proj / "index.html").write_text(compose.index_html(w, h, duration), encoding="utf-8")
    (proj / "compositions" / "captions.html").write_text(compose.captions_html(groups, w, h, duration, a.accent, band, scrim=not a.no_scrim), encoding="utf-8")
    (proj / "captions.json").write_text(compose.groups_json(groups), encoding="utf-8")
    check = hf(proj, "check", "--json", check=False)
    (proj / "check.json").write_text(check.stdout, encoding="utf-8")
    if check.returncode != 0:
        shell.log("hyperframes check reported problems; see check.json (rendering anyway, judge from the frames)")
    silent = proj / "render.mp4"
    hf(proj, "render", "--quality", "draft" if a.draft else "delivery", "--output", str(silent.resolve()))
    shell.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(silent), "-i", a.video,
               "-map", "0:v", "-map", "1:a", "-c", "copy", "-shortest", "-movflags", "+faststart", a.out])
    shell.log(f"{len(groups)} caption groups -> {a.out}")


if __name__ == "__main__":
    main()
