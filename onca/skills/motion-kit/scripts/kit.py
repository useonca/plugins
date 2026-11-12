"""The motion kit's command line: start a project, sync its cues, fill its brand, find the beats of a bed, place
sound effects, build the music call, cut out a product photo and turn a recipe into cues.

usage: kit.py new PROJECT [--size 1080x1920] [--fps 30] [--duration 12]
       kit.py sync PROJECT
       kit.py brand PROJECT --kit KIT.json [--fonts DIR]...
       kit.py check PROJECT
       kit.py shot PAGE.html OUT.png [--width 390] [--height 844] [--scale 3] [--no-trim]
       kit.py voice PROJECT --lines LINES.json [--asr WORDS.json] [--max-pause 0.28 | --keep-pauses] [--tempo 1.0] [--raw]
       kit.py pick CHOICES.json --out PICK.json [--minutes 10] [--no-open]
       kit.py beats PROJECT --music BED
       kit.py sound PROJECT --video RENDER.mp4 [--music BED] [--music-db -18] [--voice VOICE.wav]
                    [--out timeline.json] [--no-render]
       kit.py music params --prompt TEXT --seconds S [--model elevenlabs_music_v2_5] [--price-check]
       kit.py music record PROJECT --file BED --model M --prompt TEXT --seconds S --credits C --job JOB [--call ID]
       kit.py cutout IN OUT.png [--engine vision|rembg] [--trim]
       kit.py recipe check RECIPE.json
       kit.py recipe cues RECIPE.json --out FILE

Run it with python3 (macOS, Linux) or py -3 -X utf8 (Windows). Exit codes: 0 ok, 2 bad input (every problem, one per
line), 1 a tool failed (named, with its last lines). Nothing here installs anything or calls the internet; `pick`
serves one page on this machine only (127.0.0.1) until the founder clicks or the time runs out.
"""

from __future__ import annotations

import argparse
import datetime
import json
import platform as host
import re
import shutil
import subprocess
import sys
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
SKILLS = SKILL.parent
ASSETS = SKILL / "assets"
RENDER = SKILLS / "video-render" / "scripts"
EDIT = SKILLS / "video-edit" / "scripts"
for folder in (HERE, RENDER, EDIT):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))
import kit_core  # noqa: E402
import music_core  # noqa: E402
import picker  # noqa: E402
import recipe_core  # noqa: E402
import sound_core  # noqa: E402
import timeline_core  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def log(step: str, text: str) -> None:
    print(f"[motion-kit] {step} {text}".encode("ascii", "replace").decode("ascii"), file=sys.stderr)


def bad_input(problems) -> None:
    for p in problems:
        print(p, file=sys.stderr)
    raise SystemExit(2)


def tool_failed(name: str, detail: str = "") -> None:
    print(f"{name} failed" + (f": {detail}" if detail else ""), file=sys.stderr)
    raise SystemExit(1)


def load_text(path: Path) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def save_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def read_json(path: Path, what: str):
    try:
        return json.loads(load_text(path))
    except OSError:
        bad_input([f"{what}: {path} is missing"])
    except ValueError as e:
        bad_input([f"{what}: {path} is not valid JSON ({e})"])


def write_json(path: Path, data) -> None:
    save_text(path, json.dumps(data, indent=1, ensure_ascii=False) + "\n")


def run(cmd: list, name: str) -> subprocess.CompletedProcess:
    """A tool run without a shell; exit 1 naming it with its last stderr lines when it fails."""
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    except OSError as e:
        tool_failed(name, str(e))
    if done.returncode != 0:
        tail = "\n".join((done.stderr or done.stdout or "").strip().splitlines()[-8:])
        tool_failed(name, f"exit {done.returncode}\n{tail}")
    return done


def macos_major():
    version = host.mac_ver()[0]
    return int(version.split(".")[0]) if version else None


def plan() -> dict:
    return kit_core.platform_plan(sys.platform, macos_major(), bool(shutil.which("swift")))


def engine_command_line() -> list:
    """The pinned render engine's command (video-render's engine.py, which handles Mac and Windows)."""
    return kit_core.engine_command(sys.executable, RENDER / "engine.py")


def engine(args: list, name: str = "the render engine") -> subprocess.CompletedProcess:
    return run(engine_command_line() + args, name)


# ---------------------------------------------------------------- new

PAGE = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="stylesheet" href="kit/motion.css" />
    <link rel="stylesheet" href="brand.css" />
    <style>
      html, body { margin: 0; padding: 0; width: __W__px; height: __H__px; overflow: hidden; background: var(--om-paper); }
      #main { position: relative; width: __W__px; height: __H__px; overflow: hidden; }
      #headline { position: absolute; left: 90px; right: 90px; top: 760px; margin: 0; }
    </style>
  </head>
  <body>
    <div id="main" data-composition-id="main" data-start="0" data-duration="__DUR__" data-width="__W__" data-height="__H__"
         data-motion-blur="on" data-motion-blur-events="on" data-no-timeline>
      <h1 id="headline" class="om-title">Your headline, word by word</h1>
    </div>
    <script src="kit/motion.js"></script>
    <script src="cues.js"></script>
    <script>OncaMotion.seek(0);</script>
  </body>
</html>
"""


def copy_kit(project: Path) -> None:
    kit = project / "kit"
    kit.mkdir(parents=True, exist_ok=True)
    for name in ("motion.js", "motion.css"):
        shutil.copy2(ASSETS / "kit" / name, kit / name)
    for folder in ("props", "paper", "fonts"):
        if (ASSETS / folder).exists():
            shutil.copytree(ASSETS / folder, kit / folder, dirs_exist_ok=True)


def cmd_new(a) -> None:
    project = Path(a.project)
    size = re.fullmatch(r"(\d+)x(\d+)", a.size)
    problems = []
    if project.exists() and (not project.is_dir() or any(project.iterdir())):
        problems.append(f"{project} is not an empty folder; pick a new one")
    if not size:
        problems.append(f"size must be WIDTHxHEIGHT, like 1080x1920, not {a.size!r}")
    if a.fps <= 0 or a.duration <= 0:
        problems.append("fps and duration must be over 0")
    if problems:
        bad_input(problems)
    w, h = int(size.group(1)), int(size.group(2))
    project.mkdir(parents=True, exist_ok=True)
    copy_kit(project)
    page = PAGE.replace("__W__", str(w)).replace("__H__", str(h)).replace("__DUR__", f"{a.duration:g}")
    save_text(project / "index.html", page)
    doc = {"version": 1, "fps": a.fps, "size": [w, h], "duration": a.duration,
           "cues": [{"id": "headline", "part": "words", "at": 0.3, "params": {"mode": "ink"}}]}
    write_json(project / "cues.json", doc)
    write_json(project / "brand.json", {})
    sync(project)
    log("new", f"{project} ({w}x{h}, {a.fps} fps, {a.duration:g} s)")


# ---------------------------------------------------------------- sync


def synced(project: Path) -> tuple:
    """(doc, notes): cues.json validated against the page and brand, with the voice's words, item counts and
    beat snaps applied: what cues.js holds and what the sound follows. Exit 2 on any problem."""
    doc = read_json(project / "cues.json", "cues")
    html = load_text(project / "index.html") if (project / "index.html").exists() else ""
    problems = [] if html else [f"{project / 'index.html'} is missing"]
    problems += kit_core.validate_cues(doc, kit_core.html_ids(html))
    brand = read_json(project / "brand.json", "brand") if (project / "brand.json").exists() else {}
    problems += kit_core.validate_brand(brand)
    words = None
    cues = doc.get("cues") if isinstance(doc, dict) else None
    placed = project / "voice-lines.json"
    if placed.exists() and isinstance(doc, dict) and kit_core._num(doc.get("duration")):
        lines = read_json(placed, "voice-lines")
        end = max((ln.get("end", 0) for ln in lines if isinstance(ln, dict)), default=0) if isinstance(lines, list) else 0
        if end > doc["duration"]:
            problems.append(f"duration: the voice (voice-lines.json) ends at {end:g} s, past {doc['duration']:g}; "
                            f"set duration to {end + 0.5:g} or more, or the end of the voice is cut")
    voiced = [c for c in cues if kit_core.voiced(c) or kit_core.word_timed(c)] if isinstance(cues, list) else []
    if voiced:
        if not isinstance(doc.get("words"), str):
            problems.append(f"{voiced[0].get('id')}: uses the voice's words, so cues.json needs `words` (a words.json path)")
        else:
            path = project / doc["words"]
            try:
                words = json.loads(load_text(path))
                if isinstance(words, dict):
                    words = words.get("words", [])
            except (OSError, ValueError):
                problems.append(f"words: cannot read {path}")
    notes = []
    if not problems and words is not None:  # word times first: snapping and the voice's words read the final at
        cues, more = kit_core.resolve_word_times(cues, words)
        problems += more
    if problems:
        bad_input(problems)
    if (project / "beats.json").exists():  # snap first, so voice times are taken from the cue's final at
        cues, notes = kit_core.snap(cues, read_json(project / "beats.json", "beats"))
    if words is not None:
        cues = kit_core.voice_words(cues, words)
    out = kit_core.with_counts(dict(doc, cues=cues), html)
    return out, notes, brand


ROOT_TAG = re.compile(r'<[^>]*\bid="main"[^>]*>', re.S)
DURATION_ATTR = re.compile(r'(\bdata-duration=")[^"]*(")')


def sync(project: Path) -> dict:
    doc, notes, brand = synced(project)
    save_text(project / "cues.js", kit_core.cues_js(doc))
    save_text(project / "brand.css", kit_core.brand_css(brand))
    html = load_text(project / "index.html")
    root = ROOT_TAG.search(html)
    if root and DURATION_ATTR.search(root.group(0)):
        tag = DURATION_ATTR.sub(lambda m: m.group(1) + f"{float(doc['duration']):g}" + m.group(2), root.group(0), count=1)
        fixed = html[:root.start()] + tag + html[root.end():]
        if fixed != html:
            save_text(project / "index.html", fixed)
    else:
        log("sync", "warning: no #main root with data-duration in index.html, so its length was not set")
    for n in notes:
        log("snap", n)
    for family in kit_core.brand_fonts(brand):
        log("sync", f"warning: no font file for {family!r}: run kit.py brand with --fonts, else the render falls back")
    log("sync", f"{len(doc['cues'])} cues -> {(project / 'cues.js').as_posix()}, brand.css")
    return doc


def cmd_sync(a) -> None:
    sync(Path(a.project))


# ---------------------------------------------------------------- brand


def cmd_brand(a) -> None:
    project = Path(a.project)
    kit = read_json(Path(a.kit), "kit")
    if isinstance(kit, dict) and isinstance(kit.get("brand_kit"), dict):
        kit = kit["brand_kit"]
    brand = read_json(project / "brand.json", "brand") if (project / "brand.json").exists() else {}
    problems = kit_core.validate_brand(brand) + ([] if isinstance(kit, dict) else ["kit: a get_brand_kit answer is an object"])
    if problems:
        bad_input(problems)
    filled = kit_core.brand_from_kit(kit, brand)
    kit_fonts = [f.get("name") for f in (kit.get("fonts") or []) if isinstance(f, dict)]
    found = find_fonts(project, kit_core.brand_fonts(filled, kit_fonts), [Path(d) for d in a.fonts or []])
    if found:
        filled["font_files"] = dict(filled.get("font_files") or {}, **found)
    write_json(project / "brand.json", filled)
    save_text(project / "brand.css", kit_core.brand_css(filled))
    log("brand", f"{len(set(filled) - set(brand))} tokens filled from the kit -> brand.json, brand.css")


def find_fonts(project: Path, families: list, extra: list) -> dict:
    """{family: fonts/FILE} for each family whose file is found (the project's fonts/, the given folders, then
    the system's), copied into PROJECT/fonts/; each family not found is named with where to get it."""
    import os
    folders = [project / "fonts", *extra, *kit_core.font_dirs(sys.platform, Path.home(), dict(os.environ))]
    listed = {}  # folder -> {file name: path}, each folder walked once
    found = {}
    for family in families:
        for folder in folders:
            if not folder.is_dir():
                continue
            if folder not in listed:
                listed[folder] = {p.name: p for p in folder.rglob("*") if p.suffix.lower() in kit_core.FONT_SUFFIXES}
            best = kit_core.pick_font_file(family, list(listed[folder]))
            if best:
                src = listed[folder][best]
                dest = project / "fonts" / best
                dest.parent.mkdir(parents=True, exist_ok=True)
                if src.resolve() != dest.resolve():
                    shutil.copy2(src, dest)
                found[family] = f"fonts/{best}"
                log("brand", f"font {family!r}: {src.as_posix()} -> {found[family]}")
                break
        else:
            log("brand", f"font {family!r}: no file found; download its files (an OFL or the founder's own licence) into "
                         f"{(project / 'fonts').as_posix()} and run brand again. Google Fonts lists them at "
                         f"{kit_core.google_fonts_link(family)}")
    return found


# ---------------------------------------------------------------- check


def cmd_check(a) -> None:
    project = Path(a.project).resolve()
    done = subprocess.run(engine_command_line() + ["check", "--json"], cwd=project, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    text = done.stdout or ""
    try:  # the report is the first JSON object; npx may print notices around it
        report, _ = json.JSONDecoder().raw_decode(text[text.index("{"):])
    except ValueError:
        tool_failed("the render engine's check", "\n".join((done.stderr or text).strip().splitlines()[-8:]))
    save_text(project / "check.json", json.dumps(report, indent=1))
    summary = kit_core.check_summary(report)
    labels = {"errors": "error", "warnings": "warning", "expected": "expected (kit.py sound adds the sound)"}
    for kind, label in labels.items():
        for line in summary[kind]:
            print(f"{label}: {line}")
    log("check", f"{len(summary['errors'])} errors, {len(summary['warnings'])} warnings, "
                 f"{len(summary['expected'])} expected -> {(project / 'check.json').as_posix()}")
    if summary["errors"]:
        raise SystemExit(1)


# ---------------------------------------------------------------- shot


def find_chrome():
    import os
    for c in kit_core.chrome_candidates(sys.platform, dict(os.environ)):
        if Path(c).is_file():
            return c
        if shutil.which(c):
            return shutil.which(c)
    return None


def cmd_shot(a) -> None:
    import tempfile
    page, out = Path(a.page).resolve(), Path(a.out).resolve()
    if not page.is_file():
        bad_input([f"page: {page} is missing"])
    chrome = find_chrome()
    if not chrome:
        tool_failed("Chrome", f"not found: {plan()['install']['chrome']}")
    profile = tempfile.mkdtemp(prefix="motion-kit-chrome-")
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        run(kit_core.shot_command(chrome, page.as_uri(), out, a.width, a.height, a.scale, profile), "Chrome's screenshot")
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    if not out.exists():
        tool_failed("Chrome's screenshot", f"no file at {out}")
    if a.no_trim:
        w, h = kit_core.png_size(out.read_bytes())
    else:
        w, h, rows = kit_core.trim(*kit_core.read_png(out.read_bytes()))
        out.write_bytes(kit_core.write_png(w, h, rows))
    log("shot", f"{page.name} at {a.scale:g}x -> {out.as_posix()} ({w}x{h} px, show it at {w / a.scale:g} px wide)")


# ---------------------------------------------------------------- voice lines


def media_seconds(path: Path):
    seconds = wav_seconds(path)
    if seconds is not None:
        return seconds
    probe = shutil.which("ffprobe")
    if not probe:
        return None
    done = subprocess.run([probe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    try:
        return float(done.stdout.strip())
    except ValueError:
        return None


def tighten(ffmpeg: str, src: Path, out: Path, max_pause) -> tuple:
    """(seconds before, seconds after, pauses cut): the line decoded to 48 kHz mono, its quiet ends trimmed and
    its long pauses cut (kit_core.keep_spans on video-edit's levels and quiet floor), written to `out`."""
    from array import array
    try:
        done = subprocess.run([ffmpeg, "-v", "error", "-i", str(src), "-ac", "1", "-ar", "48000", "-f", "s16le", "-"],
                              capture_output=True)
    except OSError as e:
        tool_failed(f"ffmpeg's decode of {src.name}", str(e))
    if done.returncode:
        tool_failed(f"ffmpeg's decode of {src.name}", done.stderr.decode("utf-8", "replace").strip()[-800:])
    samples = array("h", done.stdout[:len(done.stdout) // 2 * 2])  # little-endian, as on every supported machine
    levels = kit_core.edit_core.levels_db(samples, 48000)
    spans = kit_core.keep_spans(levels, kit_core.edit_core.quiet_floor(levels), max_pause)
    kept = array("h")
    for start, end in spans or [(0, len(samples) / 48000)]:
        piece = samples[int(start * 48000):int(end * 48000)]
        if spans:
            kit_core.fade_edges(piece, 48000)
        kept += piece
    out.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(48000)
        w.writeframes(kept.tobytes())
    return len(samples) / 48000, len(kept) / 48000, max(0, len(spans) - 1)


def cmd_voice(a) -> None:
    project = Path(a.project)
    doc = read_json(Path(a.lines), "lines")
    problems = kit_core.validate_lines(doc)
    low, high = kit_core.TEMPO_RANGE
    if not low <= a.tempo <= high:
        problems.append(f"--tempo must be {low:g} to {high:g} (a gentle change), got {a.tempo:g}")
    if a.max_pause is not None and a.max_pause < 0.1:
        problems.append(f"--max-pause must be 0.1 s or more, got {a.max_pause:g}")
    base = Path(a.lines).resolve().parent
    sources = {}
    for ln in doc.get("lines", []) if not problems else []:
        sources[ln["id"]] = (base / ln["file"]).resolve()
        if not sources[ln["id"]].exists():
            problems.append(f"line {ln['id']}: cannot read {sources[ln['id']]}")
    if problems:
        bad_input(problems)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        tool_failed("ffmpeg", f"not found: {plan()['install']['ffmpeg']}")
    durations = {}
    for ln in doc["lines"]:
        path = sources[ln["id"]]
        if a.raw:  # a take already edited by hand
            seconds = media_seconds(path)
            if seconds is None:
                bad_input([f"line {ln['id']}: cannot read {path}"])
        else:
            path = (project / "voice-lines" / f"{ln['id']}.wav").resolve()
            before, seconds, cut = tighten(ffmpeg, sources[ln["id"]], path, None if a.keep_pauses else a.max_pause)
            log("voice", f"line {ln['id']}: {before:.2f} -> {seconds:.2f} s (quiet ends trimmed"
                         + (f", {cut} long pauses cut to {a.max_pause:g} s)" if cut else ")"))
        durations[ln["id"]] = seconds / a.tempo
        ln["file"] = path.as_posix()
    try:
        placed = kit_core.place_lines(doc["lines"], durations, float(doc.get("lead", 0.3)), float(doc.get("gap", 0.25)))
    except ValueError as e:
        bad_input([str(e)])
    asr = None
    if a.asr:
        asr = read_json(Path(a.asr), "asr")
        asr = asr.get("words", []) if isinstance(asr, dict) else asr
        inside = [w for w in asr if any(p["at"] - 0.05 <= w.get("start", -1) < p["end"] + 0.05 for p in placed)]
        if len(inside) < len(asr) / 2:
            log("voice", "warning: most --asr words fall outside the placed lines, so their times are not used: "
                         "--asr must be the transcript of this project's voice.wav (run voice, transcribe voice.wav, run voice again)")
    cues = read_json(project / "cues.json", "cues") if (project / "cues.json").exists() else {}
    seconds = max(float(cues.get("duration") or 0), placed[-1]["end"] + 0.5)  # never cut the voice
    if cues.get("duration") and placed[-1]["end"] > float(cues["duration"]):
        log("voice", f"note: the voice ends at {placed[-1]['end']:g} s, past the video's {float(cues['duration']):g} s: "
                     f"set cues.json duration to {placed[-1]['end'] + 0.5:g}, then kit.py sync sets the page's length "
                     "(sync stops until it fits)")
    run([ffmpeg] + kit_core.voice_mix_args(placed, seconds, (project / "voice.wav").resolve(), a.tempo), "ffmpeg's voice mix")
    write_json(project / "words.json", kit_core.script_words(placed, asr))
    write_json(project / "voice-lines.json", placed)
    log("voice", f"{len(placed)} lines, {placed[0]['at']:g} to {placed[-1]['end']:g} s"
                 + (f" at tempo {a.tempo:g}" if a.tempo != 1 else "")
                 + f" -> voice.wav, words.json (the script's spelling, each word with its line; times "
                 f"{'from the recognised words' if asr else 'spread by length'}), voice-lines.json")


# ---------------------------------------------------------------- pick


def cmd_pick(a) -> None:
    doc = read_json(Path(a.choices), "choices")
    problems = kit_core.validate_choices(doc)
    base = Path(a.choices).resolve().parent
    for c in doc.get("choices", []) if not problems else []:
        c["file"] = (base / c["file"]).resolve()
        if not c["file"].is_file():
            problems.append(f"choice {c['id']}: {c['file']} is missing")
    if problems:
        bad_input(problems)
    picked = picker.serve(doc.get("title") or "Pick a voice", doc["choices"], a.minutes * 60, not a.no_open, log)
    if picked is None:
        tool_failed("the picker", f"no pick within {a.minutes:g} minutes; ask the founder in chat instead")
    write_json(Path(a.out), {"id": picked["id"], "name": picked["name"],
                             "picked_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
    log("pick", f"{picked['name']!r} -> {Path(a.out).as_posix()}")


# ---------------------------------------------------------------- beats


def cmd_beats(a) -> None:
    project, bed = Path(a.project), Path(a.music)
    if not bed.exists():
        bad_input([f"music: {bed} is missing"])
    done = engine(["beats", str(bed.resolve()), "--json"])
    try:
        data = json.loads(done.stdout[done.stdout.index("{"):])
        beat_times = [round(float(t), 3) for t in data["beatTimes"]]
        out = {"bpm": data.get("bpm"), "bpmConfidence": data.get("bpmConfidence", 0), "beatTimes": beat_times,
               "bars": kit_core.bars(beat_times)}
    except (ValueError, KeyError, TypeError):
        tool_failed("the render engine", "beats gave no beat list")
    write_json(project / "beats.json", out)
    log("beats", f"{len(beat_times)} beats at {out['bpm']} bpm (confidence {out['bpmConfidence']}) -> beats.json")


# ---------------------------------------------------------------- sound


def sfx_index() -> dict:
    index = read_json(ASSETS / "sfx" / "sfx.json", "sfx")
    return {name: [dict(t, file=(ASSETS / "sfx" / t["file"]).as_posix()) for t in takes] for name, takes in index.items()}


def silence(path: Path, seconds: float, rate: int = 48000) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(round(seconds * rate)))


def wav_seconds(path: Path):
    try:
        with wave.open(str(path), "rb") as w:
            return w.getnframes() / float(w.getframerate())
    except (wave.Error, OSError, EOFError):
        return None


def padded(voice: Path, seconds: float, out: Path) -> Path:
    """The voice, or a copy of it padded with silence to `seconds` (the mix ends where the voice track ends)."""
    with wave.open(str(voice), "rb") as w:
        params, frames = w.getparams(), w.readframes(w.getnframes())
    missing = int(round(seconds * params.framerate)) - params.nframes
    if missing <= 0:
        return voice
    with wave.open(str(out), "wb") as w:
        w.setparams(params)
        w.writeframes(frames + b"\x00" * (missing * params.sampwidth * params.nchannels))
    log("sound", f"voice is {params.nframes / params.framerate:.2f} s, padded with silence to {seconds:g} s -> {out.as_posix()}")
    return out


def cmd_sound(a) -> None:
    project = Path(a.project)
    problems = [f"{name}: {p} is missing" for name, p in (("video", a.video), ("music", a.music), ("voice", a.voice))
                if p and not Path(p).exists()]
    if problems:
        bad_input(problems)
    doc, _, _ = synced(project)
    index = sfx_index()
    hit_list = sound_core.hits(doc)
    placed = sound_core.place(hit_list, index, int(doc.get("fps", 30)))
    if a.voice:
        if wav_seconds(Path(a.voice)) is None:
            bad_input([f"voice: {a.voice} must be a PCM WAV (ffmpeg -i IN -ar 48000 -ac 1 -c:a pcm_s16le OUT.wav)"])
        voice = padded(Path(a.voice).resolve(), float(doc["duration"]), (project / "voice-padded.wav").resolve())
    else:
        voice = (project / "silence.wav").resolve()
        silence(voice, float(doc["duration"]))
    music = Path(a.music).resolve().as_posix() if a.music else None
    tl = sound_core.timeline(doc, Path(a.video).resolve().as_posix(), placed, music, voice.as_posix(), a.music_db)
    durations = {"main": float(doc["duration"]), "voice": wav_seconds(voice)}
    for take in (t for takes in index.values() for t in takes):
        durations[sound_core._key(take["file"])] = take["dur"]
    problems = timeline_core.validate(tl, {k: v for k, v in durations.items() if v is not None})
    if problems:
        bad_input([f"timeline: {p}" for p in problems])
    out = Path(a.out) if a.out else project / "timeline.json"
    write_json(out, tl)
    log("sound", f"{len(hit_list)} hits, {len(placed)} effects placed -> {out.as_posix()}")
    if a.no_render:
        return
    run([sys.executable, str(EDIT / "timeline.py"), "render", str(out), "--dir", str(project / "out")], "video-edit's timeline render")
    log("sound", f"rendered -> {(project / 'out' / 'with-sound.mp4').as_posix()}")


# ---------------------------------------------------------------- music


def cmd_music_params(a) -> None:
    try:
        out = music_core.params(a.model, a.prompt, a.seconds, a.price_check)
    except ValueError as e:
        bad_input([str(e)])
    print(json.dumps(out))


def cmd_music_record(a) -> None:
    project, bed = Path(a.project), Path(a.file)
    if not bed.exists():
        bad_input([f"file: {bed} is missing"])
    now = datetime.datetime.now(datetime.timezone.utc)
    try:
        rec = music_core.record(a.model, a.prompt, a.seconds, a.credits, a.job, a.call, now)
    except ValueError as e:
        bad_input([str(e)])
    (project / "music").mkdir(parents=True, exist_ok=True)
    dest = project / "music" / bed.name
    if bed.resolve() != dest.resolve():
        shutil.copy2(bed, dest)
    rec["file"] = dest.relative_to(project).as_posix()
    write_json(project / "music.json", rec)
    log("music", f"{rec['model']}, {a.seconds:g} s, {a.credits:g} credits -> music.json, {rec['file']}")


# ---------------------------------------------------------------- cutout


def cmd_cutout(a) -> None:
    src, out = Path(a.src), Path(a.out)
    if not src.exists():
        bad_input([f"{src} is missing"])
    p = plan()
    route = a.engine or p["cutout"]
    rembg = kit_core.rembg_line()
    if route == "vision":
        swift = shutil.which("swift")
        if not swift:
            tool_failed("cutout", f"Apple Vision needs swift: {p['install'].get('swift', 'xcode-select --install')}; "
                                  f"or cut out with rembg (uv: {p['install']['uv']}): {rembg}")
        cmd = kit_core.cutout_command("vision", src.resolve(), out.resolve(), swift, None)
    else:
        uv = shutil.which("uv")
        if not uv:
            swift_hint = f"; on macOS 14 or newer Apple Vision needs only swift: {p['install']['swift']}" if "swift" in p["install"] else ""
            tool_failed("cutout", f"rembg runs through uv: {p['install']['uv']}, then: {rembg}{swift_hint}")
        cmd = kit_core.cutout_command("rembg", src.resolve(), out.resolve(), None, uv)
    out.parent.mkdir(parents=True, exist_ok=True)
    run(cmd, f"cutout ({route})")
    if a.trim:
        try:
            w, h, rows = kit_core.trim(*kit_core.read_png(out.read_bytes()))
            out.write_bytes(kit_core.write_png(w, h, rows))
        except ValueError as e:
            log("cutout", f"trim skipped: {e}")
    log("cutout", f"{route}: {src.name} -> {out.as_posix()}")


# ---------------------------------------------------------------- recipe


def load_recipe(path: str) -> dict:
    recipe = read_json(Path(path), "recipe")
    problems = recipe_core.validate(recipe)
    if problems:
        bad_input(problems)
    return recipe


def cmd_recipe_check(a) -> None:
    recipe = load_recipe(a.recipe)
    log("recipe", f"ok: {len(recipe['beats'])} beats")


def cmd_recipe_cues(a) -> None:
    doc = recipe_core.skeleton(load_recipe(a.recipe))
    write_json(Path(a.out), doc)
    log("recipe", f"{len(doc['cues'])} cues -> {Path(a.out).as_posix()}")


# ---------------------------------------------------------------- main


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="The Onca motion kit.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("new", help="start a project folder")
    s.add_argument("project")
    s.add_argument("--size", default="1080x1920")
    s.add_argument("--fps", type=int, default=30)
    s.add_argument("--duration", type=float, default=12.0)
    s.set_defaults(fn=cmd_new)
    s = sub.add_parser("sync", help="validate cues.json and write cues.js and brand.css")
    s.add_argument("project")
    s.set_defaults(fn=cmd_sync)
    s = sub.add_parser("brand", help="fill unset brand tokens from a saved get_brand_kit answer")
    s.add_argument("project")
    s.add_argument("--kit", required=True)
    s.add_argument("--fonts", action="append", help="a folder to look for the brand's font files in (repeatable)")
    s.set_defaults(fn=cmd_brand)
    s = sub.add_parser("check", help="the render engine's check, with the findings the kit expects set apart")
    s.add_argument("project")
    s.set_defaults(fn=cmd_check)
    s = sub.add_parser("shot", help="a crisp screenshot of an HTML page or card at 3x, trimmed")
    s.add_argument("page")
    s.add_argument("out")
    s.add_argument("--width", type=int, default=390)
    s.add_argument("--height", type=int, default=844)
    s.add_argument("--scale", type=float, default=3)
    s.add_argument("--no-trim", action="store_true")
    s.set_defaults(fn=cmd_shot)
    s = sub.add_parser("voice", help="place the narration's line files into voice.wav and words.json")
    s.add_argument("project")
    s.add_argument("--lines", required=True)
    s.add_argument("--asr")
    s.add_argument("--max-pause", type=float, default=kit_core.MAX_PAUSE)
    s.add_argument("--keep-pauses", action="store_true")
    s.add_argument("--tempo", type=float, default=1.0)
    s.add_argument("--raw", action="store_true")
    s.set_defaults(fn=cmd_voice)
    s = sub.add_parser("pick", help="a page where the founder plays each choice and clicks one")
    s.add_argument("choices")
    s.add_argument("--out", required=True)
    s.add_argument("--minutes", type=float, default=10)
    s.add_argument("--no-open", action="store_true")
    s.set_defaults(fn=cmd_pick)
    s = sub.add_parser("beats", help="the beats of a music bed -> beats.json")
    s.add_argument("project")
    s.add_argument("--music", required=True)
    s.set_defaults(fn=cmd_beats)
    s = sub.add_parser("sound", help="place sound effects and mix them with video-edit's timeline")
    s.add_argument("project")
    s.add_argument("--video", required=True)
    s.add_argument("--music")
    s.add_argument("--music-db", type=float, default=-18)
    s.add_argument("--voice")
    s.add_argument("--out")
    s.add_argument("--no-render", action="store_true")
    s.set_defaults(fn=cmd_sound)
    m = sub.add_parser("music", help="the Higgsfield music call and its licence record").add_subparsers(dest="music_cmd", required=True)
    s = m.add_parser("params", help="print the params of higgsfield_generate_audio")
    s.add_argument("--prompt", required=True)
    s.add_argument("--seconds", type=float, required=True)
    s.add_argument("--model", default="elevenlabs_music_v2_5")
    s.add_argument("--price-check", action="store_true")
    s.set_defaults(fn=cmd_music_params)
    s = m.add_parser("record", help="keep the bed and its licence record in the project")
    s.add_argument("project")
    s.add_argument("--file", required=True)
    s.add_argument("--model", required=True)
    s.add_argument("--prompt", required=True)
    s.add_argument("--seconds", type=float, required=True)
    s.add_argument("--credits", type=float, required=True)
    s.add_argument("--job", required=True)
    s.add_argument("--call")
    s.set_defaults(fn=cmd_music_record)
    s = sub.add_parser("cutout", help="cut a product photo out of its background")
    s.add_argument("src")
    s.add_argument("out")
    s.add_argument("--engine", choices=("vision", "rembg"))
    s.add_argument("--trim", action="store_true")
    s.set_defaults(fn=cmd_cutout)
    r = sub.add_parser("recipe", help="check a recipe or turn it into cues").add_subparsers(dest="recipe_cmd", required=True)
    s = r.add_parser("check")
    s.add_argument("recipe")
    s.set_defaults(fn=cmd_recipe_check)
    s = r.add_parser("cues")
    s.add_argument("recipe")
    s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_recipe_cues)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
