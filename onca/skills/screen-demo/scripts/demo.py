#!/usr/bin/env python3
"""Build a long, chaptered, narrated 16:9 demo (YouTube) from a storyboard: footage clips, title cards, one
WAV per spoken scene, chapter labels and captions. Free and local, through Onca's render engine.

usage: demo.py build DEMO.json --out DIR [--burn-captions] [--draft]

DEMO.json: {"title", "size": "1920x1080", "chapters": [{"title", "scenes": [{"id", "say", "audio", "clip",
"clip_from", "card", "min"}]}]}. Paths are relative to DEMO.json. A scene that speaks needs its WAV at `audio`
(default voice/<id>.wav: `voice/scripts/say.py --storyboard DEMO.json --out voice` makes them with the
built-in voice; any WAV there is used as is). Writes DIR/<name>.mp4 (name: the storyboard's folder, or the
file's stem when that is not demo.json), DIR/chapters.txt (the YouTube description lines),
DIR/captions.srt, DIR/captions.vtt, the project (<name>-hf/) and a contact sheet.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import demo_core  # noqa: E402
import demo_html  # noqa: E402
import shared  # noqa: E402


def output_name(storyboard: Path) -> str:
    return storyboard.resolve().parent.name if storyboard.name == "demo.json" else storyboard.stem


def build(a) -> None:
    path = Path(a.storyboard)
    try:
        sb = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        shared.bad_input([f"no storyboard at {path}"])
    except ValueError as e:
        shared.bad_input([f"{path} is not JSON: {e}"])
    problems = demo_core.storyboard_problems(sb)
    if problems:
        shared.bad_input(problems)
    base = path.resolve().parent
    w, h = shared.parse_size(sb.get("size", "1920x1080"))
    voice: dict[str, float] = {}
    missing = []
    for ch in sb["chapters"]:
        for scene in ch["scenes"]:
            if scene.get("clip") and not (base / scene["clip"]).exists():
                missing.append(f"scene {scene['id']!r}: clip {scene['clip']} not found")
            if demo_core.speaks(scene):
                wav = base / demo_core.voice_path(scene)
                if wav.exists():
                    voice[scene["id"]] = shared.probe(wav)["duration"]
                elif scene.get("audio"):
                    missing.append(f"scene {scene['id']!r}: no audio at {scene['audio']}")
                else:
                    missing.append(f"scene {scene['id']!r}: no voice at {demo_core.voice_path(scene)} "
                                   f"(run voice/scripts/say.py --storyboard {path.name} --out voice)")
    if missing:
        shared.bad_input(missing)
    tl = demo_core.timeline(sb, voice)
    duration = tl[-1]["end"]
    marks = demo_core.chapter_marks(tl)
    for p in demo_core.chapter_problems(marks, duration):
        shared.log(f"warning: {p} (YouTube will not show chapters)")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    name = output_name(path)
    proj = out / f"{name}-hf"
    (proj / "assets").mkdir(parents=True, exist_ok=True)
    for s in tl:
        if s["clip"]:
            dst = f"assets/clip-{s['id']}{Path(s['clip']).suffix}"
            shutil.copyfile(base / s["clip"], proj / dst)
            s["clip"] = dst
        if s["audio"]:
            dst = f"assets/voice-{s['id']}.wav"
            shutil.copyfile(base / s["audio"], proj / dst)
            s["audio"] = dst
    cue_list = demo_core.cues(tl)
    (out / "captions.srt").write_text(demo_core.srt(cue_list), encoding="utf-8")
    (out / "captions.vtt").write_text(demo_core.vtt(cue_list), encoding="utf-8")
    (out / "chapters.txt").write_text(demo_core.description(sb["title"], marks), encoding="utf-8")
    (proj / "timeline.json").write_text(json.dumps(tl, indent=1), encoding="utf-8")
    fonts = demo_core.fonts_for(sb)
    (proj / "index.html").write_text(demo_html.index_html(tl, marks, w, h, duration,
                                                          captions=cue_list if a.burn_captions else None, fonts=fonts), encoding="utf-8")
    missing = shared.fonts_loaded(proj / "index.html", [f'700 76px "{fonts["display"]}"', f'400 34px "{fonts["text"]}"'])
    if missing:
        print(f"fonts did not load: {', '.join(missing)} (offline, or a name Google Fonts does not have); "
              "a fallback font fails review", file=sys.stderr)
        raise SystemExit(1)
    shared.log(f"{len(tl)} scenes, {len(marks)} chapters, {len(voice)} voiced, {duration} s")
    raw = proj / "render.mp4"
    shared.render(proj, raw, a.draft)
    video = out / f"{name}.mp4"
    shared.finish(raw, video, sound=bool(voice))
    sheet = shared.contact(video, duration)
    shared.log(f"-> {video}, {out / 'chapters.txt'}, captions.srt, captions.vtt (contact sheet {sheet})")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Build a long, chaptered, narrated demo from a storyboard.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="render DEMO.json into DIR")
    b.add_argument("storyboard")
    b.add_argument("--out", required=True)
    b.add_argument("--burn-captions", action="store_true", help="draw the captions into the picture too")
    b.add_argument("--draft", action="store_true")
    build(ap.parse_args(argv))


if __name__ == "__main__":
    main()
