"""The thin shell: subprocess calls to ffmpeg, ffprobe, the recognizer (parakeet-mlx or whisper-ctranslate2) and scenedetect.

No decisions here; core.py makes them. Every command is printed before it runs
so a log shows exactly what happened. Tools and Node 22+ are found by the
video-render skill's doctor.py (its sibling folder in this plugin), so the two
skills agree on where they look.
"""

from __future__ import annotations

import array
import base64
import functools
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "video-render" / "scripts"))
import doctor  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402
import map_core  # noqa: E402
import providers  # noqa: E402


def find_tool(name: str, path_env: str | None = None, home: Path | None = None, **kwargs) -> str | None:
    """``name`` on PATH, else in ``~/.local/bin`` (where ``uv tool install`` puts it), else (Windows) winget's
    folders; None when missing."""
    return doctor.find_tool(name, path_env, home, **kwargs)


def find_node22(path_env: str | None = None, home: Path | None = None, **kwargs) -> str | None:
    """A Node 22+ binary (PATH, Homebrew's node@22 or later, nvm's newest v22 or later), or None."""
    return doctor.find_node22(path_env, home, **kwargs)


def tool(name: str) -> str:
    """The path of ``name``, or stop with its install command (run `python3 doctor.py check` for all of them)."""
    found = find_tool(name)
    if not found:
        raise SystemExit(f"{name} not found: install it with `{doctor.install_for(doctor.current_platform(), name)}` (after the founder's yes)")
    return found


def log(msg: str) -> None:
    print(f"[video-edit] {msg}", file=sys.stderr, flush=True)


@functools.lru_cache(maxsize=None)
def _program(name: str) -> str:
    """The path doctor.py finds for ffmpeg or ffprobe (on Windows also winget's folders, which a new terminal's PATH
    may not hold yet); the bare name when it finds nothing."""
    return find_tool(name) or name


def run(cmd: list[str], *, env: dict | None = None, check: bool = True, quiet: bool = True) -> subprocess.CompletedProcess:
    if cmd and cmd[0] in ("ffmpeg", "ffprobe"):
        cmd = [_program(cmd[0]), *cmd[1:]]
    log("$ " + " ".join(_q(c) for c in cmd))
    p = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, **(env or {})}, encoding="utf-8", errors="replace")
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
    fps = core.stream_fps(v.get("r_frame_rate") if v else None, v.get("avg_frame_rate") if v else None)
    return {
        "path": str(Path(path).resolve()),
        "duration": round(float(d["format"].get("duration", 0) or 0), 3),
        "width": v and v["width"],
        "height": v and v["height"],
        "fps": fps,
        "has_audio": a is not None,
        "audio_rate": a and int(a.get("sample_rate", 0)),
        "codec": v and v.get("codec_name"),
        "profile": v and v.get("profile"),
        "pix_fmt": v and v.get("pix_fmt"),
        "time_base": v and v.get("time_base"),
        "vfr": bool(v) and core.variable_rate(v.get("r_frame_rate"), v.get("avg_frame_rate")),
        "start": round(float(d["format"].get("start_time", 0) or 0), 6),  # ffmpeg's -ss counts from here
        **{k: v.get(k) for k in ("color_primaries", "color_transfer", "color_space") if v and v.get(k) not in (None, "unknown")},
    }


def ffmpeg_log(args: list[str]) -> str:
    """Run an analysis pass (`-f null -`) and return its stderr."""
    return run(["ffmpeg", "-hide_banner", "-nostats", *args, "-f", "null", "-"]).stderr


def extract_wav(src: str | Path, dst: str | Path, rate: int = 16000, channels: int = 1) -> None:
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-vn", "-ac", str(channels), "-ar", str(rate), str(dst)])


def parakeet_json(wav: str | Path, out_dir: str | Path) -> dict:
    """Word-timed transcript (Mac). Offline first: the model is cached and the hub check alone can take minutes."""
    out_dir = Path(out_dir)
    args = [tool("parakeet-mlx"), str(wav), "--output-format", "json", "--output-dir", str(out_dir)]
    p = run(args, env={"HF_HUB_OFFLINE": "1"}, check=False)
    if p.returncode != 0:
        log("offline transcription failed (model not cached yet?), retrying online")
        run(args)
    return json.loads((out_dir / (Path(wav).stem + ".json")).read_text(encoding="utf-8"))


def asr_json(wav: str | Path, out_dir: str | Path, plat: str | None = None) -> dict:
    """The recognizer's JSON for ``wav``: parakeet-mlx on an Apple Silicon Mac, else whisper-ctranslate2 (word
    timestamps, the model downloads on the first run). ``core.words_from_asr`` reads either."""
    if (plat or doctor.current_platform()) == "mac-arm":
        return parakeet_json(wav, out_dir)
    out_dir = Path(out_dir)
    run([tool("whisper-ctranslate2"), str(wav), "--word_timestamps", "True", "--output_format", "json",
         "--output_dir", str(out_dir), "--compute_type", "auto"], quiet=False)
    return json.loads((out_dir / (Path(wav).stem + ".json")).read_text(encoding="utf-8"))


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
    shutil.rmtree(tmp, ignore_errors=True)


def scenes(src: str | Path, out_dir: str | Path) -> list[dict]:
    """Shot list from PySceneDetect (adaptive detector)."""
    out_dir = Path(out_dir)
    run([tool("scenedetect"), "-q", "-i", str(src), "-o", str(out_dir), "detect-adaptive", "list-scenes", "-f", "scenes.csv"], check=False)
    csv = out_dir / "scenes.csv"
    if not csv.exists():
        return []
    rows = [line.split(",") for line in csv.read_text(encoding="utf-8").splitlines()]
    head = next((k for k, r in enumerate(rows) if r and r[0] == "Scene Number"), None)
    if head is None:
        return []
    cols = rows[head]
    si, ei = cols.index("Start Time (seconds)"), cols.index("End Time (seconds)")
    return [{"start": float(r[si]), "end": float(r[ei])} for r in rows[head + 1:] if len(r) > ei]


# ---------------------------------------------------------------- the editor's runners


def filter_delay(chain: str, rate: int) -> float:
    """How late an audio filter chain puts its sound (a denoiser's window), measured with a click at `rate`."""
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
           f"aevalsrc='if(between(t,1,1+2/{rate}),0.9,0)':s={rate}:d=2", "-af", chain, "-ac", "1", "-f", "s16le", "-"]
    samples = _pcm(cmd)
    if not samples:
        return 0.0
    peak = max(range(len(samples)), key=lambda k: abs(samples[k]))
    return max(0.0, round(peak / rate - 1.0, 4))


def levels(src: str | Path) -> list[float]:
    """The sound's level per 10 ms (mono, 16 kHz), for placing and checking cuts in quiet."""
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"]
    log("$ " + " ".join(_q(c) for c in cmd))
    return core.levels_db(_pcm(cmd), 16000)


def _pcm(cmd: list) -> array.array:
    """The 16-bit little-endian samples an ffmpeg command writes to stdout."""
    p = subprocess.run([_program(cmd[0]), *cmd[1:]], capture_output=True)
    if p.returncode != 0:
        sys.stderr.write(p.stderr.decode(errors="replace")[-4000:])
        raise SystemExit(f"command failed ({p.returncode}): ffmpeg")
    samples = array.array("h")
    samples.frombytes(p.stdout[: len(p.stdout) // 2 * 2])
    if sys.byteorder == "big":
        samples.byteswap()
    return samples


def packets(src: str | Path, start: float = 0.0) -> tuple:
    """(keyframe times, every frame time), from the file's `start` (as -ss counts), read from the packets (no
    decoding: a 10 minute file takes a tenth of a second)."""
    p = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pts_time,flags", "-of", "csv", str(src)])
    kf = map_core.parse_keyframes("\n".join(ln.rsplit(",", 1)[0] for ln in p.stdout.splitlines() if ",K" in ln))
    pts = []
    for ln in p.stdout.splitlines():
        parts = ln.split(",")
        try:
            pts.append(float(parts[1]) - start)
        except (IndexError, ValueError):
            continue
    return ([round(t - start, 6) for t in kf] if start else kf), pts


def keyframes(src: str | Path, start: float = 0.0) -> list[float]:
    """The video's keyframe times from the file's `start`."""
    return packets(src, start)[0]


def _decode(src: str | Path, window: tuple | None = None, threads: str = "0") -> tuple:
    seek = ["-ss", f"{window[0]:.3f}", "-t", f"{window[1] - window[0]:.3f}"] if window else []
    p = run(["ffmpeg", "-hide_banner", "-nostdin", "-v", "error", "-stats", "-threads", threads, *seek, "-i", str(src),
             "-map", "0:v:0", "-f", "null", "-"], check=False)
    frames = re.findall(r"frame=\s*(\d+)", p.stderr)
    errors = [ln for ln in re.split(r"[\r\n]+", p.stderr) if ln.strip() and not re.match(r"\s*frame=", ln)]
    if p.returncode:
        errors.append(f"ffmpeg exited {p.returncode}")
    return (int(frames[-1]) if frames else 0), errors


def packet_count(src: str | Path) -> int:
    """Video packets in the file (one per frame), read from the container without decoding."""
    p = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries", "stream=nb_read_packets",
             "-of", "csv=p=0", str(src)])
    return int(p.stdout.strip().split(",")[0] or 0)


def decode_check(src: str | Path, windows: list | None = None) -> tuple:
    """(video frames, error lines). Without `windows`: one full decode on every core (about 2000 fps at 1080p on
    an M4, four times the hardware decoder). With windows (output-time spans around each join): those spans
    decoded, several at once, each from the keyframe before it, and the frames counted from the container."""
    if not windows:
        frames, errors = _decode(src)
        return frames, "\n".join(errors)
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(lambda w: _decode(src, w, "2"), windows))
    return packet_count(src), "\n".join(e for _f, errs in results for e in errs)


def aac_encoder() -> str:
    """The Mac's own AAC encoder when this ffmpeg has it (about twice as fast), else ffmpeg's."""
    return "aac_at" if "aac_at" in encoders() else "aac"


@functools.lru_cache(maxsize=1)
def encoders() -> frozenset:
    """The encoder names this ffmpeg lists (read once per run)."""
    p = run(["ffmpeg", "-hide_banner", "-encoders"])
    out = set()
    for line in p.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and len(parts[0]) == 6 and parts[0][0] in "VAS":
            out.add(parts[1])
    return frozenset(out)


@functools.lru_cache(maxsize=1)
def usable_encoders() -> frozenset:
    """The encoders this computer can really use: the ones ffmpeg lists, minus each hardware encoder whose
    one-frame trial encode fails (ffmpeg lists NVENC, QSV and AMF even with no such GPU). Read once per run."""
    listed = encoders()
    hardware = [e for e in ("h264_videotoolbox", "h264_nvenc", "h264_qsv", "h264_amf") if e in listed]
    trial = doctor.probe_hw(find_tool("ffmpeg") or "ffmpeg", doctor.current_platform(), candidates=hardware)
    failed = {enc for enc, ok in trial.items() if not ok}
    if failed:
        log("hardware encoders that failed a trial encode: " + ", ".join(sorted(failed)))
    return frozenset(listed - failed)


def encoders_for(name: str) -> frozenset:
    """The encoders to pick ``name`` from: the trial-encode result for ``auto`` or a hardware name, the plain list
    for a software one (so ``--encoder x264`` never starts a GPU trial)."""
    return usable_encoders() if name in ("auto", "videotoolbox", "nvenc", "qsv", "amf") else encoders()


def load_providers(path: str | Path | None) -> dict | None:
    """providers.json, or None; every problem printed and exit 2 when it is not valid."""
    if not path:
        return None
    try:
        config = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"providers: cannot read {path}: {exc}", file=sys.stderr)
        raise SystemExit(2)
    problems = providers.validate(config)
    if problems:
        for p in problems:
            print(f"providers: {p}", file=sys.stderr)
        raise SystemExit(2)
    return config


def run_provider(spec: dict, values: dict) -> None:
    """Run a `command` provider, or check a `file` one exists; exit 1 naming the provider and the reason."""
    name = f"provider {spec['step']} ({providers.describe(spec)})"
    if spec["kind"] == "file":
        if not Path(spec["path"]).exists():
            raise SystemExit(f"{name}: {spec['path']} does not exist")
        return
    if spec["kind"] != "command":
        return
    try:
        argv = providers.command_argv(spec, values)
    except ValueError as exc:
        raise SystemExit(f"{name}: {exc}")
    p = run(argv, check=False)
    if p.returncode != 0:
        tail = p.stderr.strip().splitlines()[-3:]
        raise SystemExit(f"{name}: exited {p.returncode}: {' | '.join(tail)}")
    out = values.get("out")
    if out and not Path(out).exists():
        raise SystemExit(f"{name}: wrote no {out}")


def timed(label: str, seconds: float, media_seconds: float | None = None) -> None:
    """The timing line of a step: `cut took 3.2 s, 41x realtime`."""
    speed = f", {media_seconds / seconds:.0f}x realtime" if media_seconds and seconds > 0 else ""
    log(f"{label} took {seconds:.1f} s{speed}")


class Clock:
    """Times a step: `with Clock("render", 30.0) as c:` logs the timing line and keeps `c.seconds`."""

    def __init__(self, label: str, media_seconds: float | None = None):
        self.label, self.media, self.seconds = label, media_seconds, 0.0

    def __enter__(self):
        self.t0 = time.monotonic()
        return self

    def __exit__(self, *exc):
        self.seconds = round(time.monotonic() - self.t0, 2)
        if exc[0] is None:
            timed(self.label, self.seconds, self.media)
        return False


def _cdp():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "screen-demo" / "scripts"))
    import cdp  # noqa: E402
    return cdp


def _open(page, path: Path) -> None:
    """Navigate to a local file and wait until it, its stylesheets and its fonts have loaded."""
    url = Path(path).resolve().as_uri()
    page.call("Page.navigate", url=url)
    ready = f"location.href === {json.dumps(url)} && document.readyState === 'complete' && document.fonts.status === 'loaded'"
    for _ in range(300):
        if page.call("Runtime.evaluate", expression=ready, returnByValue=True).get("result", {}).get("value"):
            return
        time.sleep(0.05)


def missing_fonts(page, checks: list) -> list:
    """The CSS font specs (`700 40px "Inter Tight"`) the open page could not draw in their own font."""
    expr = f"{json.dumps(checks)}.filter((f) => !document.fonts.check(f))"
    return page.call("Runtime.evaluate", expression=expr, returnByValue=True).get("result", {}).get("value") or []


def fonts_loaded(html_path: str | Path, checks: list, size: tuple = (1280, 720)) -> list:
    """Open a page in headless Chrome and return the font specs that did not load (empty when all did)."""
    with _cdp().chrome(size) as page:
        _open(page, Path(html_path))
        return missing_fonts(page, checks)


_STYLE = re.compile(r"<style>(.*?)</style>", re.S)
_BODY = re.compile(r"<body>(.*?)</body>", re.S)


def _swap(page, html_text: str) -> bool:
    """Put another caption page's style and body into the open page, keeping its loaded font (a navigation per
    caption state reloads the font each time); False when the page has no <style> or <body> to swap."""
    style, body = _STYLE.search(html_text), _BODY.search(html_text)
    if not (style and body):
        return False
    expr = (f"document.querySelector('style').textContent = {json.dumps(style.group(1))};"
            f" document.body.innerHTML = {json.dumps(body.group(1))};"
            " document.fonts.ready.then(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => r(true)))))")
    page.call("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True)
    return True


def caption_pngs(pages: dict, size: tuple, out_dir: str | Path, font_check: str | None = None) -> dict:
    """Each HTML page (key -> html) drawn by headless Chrome as a transparent PNG of `size`; key -> PNG path.
    With `font_check`, exit 1 when that font did not load (a fallback font fails review)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    with _cdp().chrome(size) as page:
        page.call("Emulation.setDefaultBackgroundColorOverride", color={"r": 0, "g": 0, "b": 0, "a": 0})
        # a headless window has a minimum height, so a short band would be cut: pin the page to the band
        page.call("Emulation.setDeviceMetricsOverride", width=size[0], height=size[1], deviceScaleFactor=1, mobile=False)
        for n, (key, html_text) in enumerate(pages.items()):
            src = out_dir / f"{key}.html"
            src.write_text(html_text, encoding="utf-8")
            if n == 0 or not _swap(page, html_text):
                _open(page, src)
            if n == 0:
                seen = page.call("Runtime.evaluate", expression="[innerWidth, innerHeight]", returnByValue=True)["result"]["value"]
                if tuple(seen) != tuple(size):
                    raise SystemExit(f"captions: the page is {seen[0]}x{seen[1]}, not the band's {size[0]}x{size[1]}; a cut caption fails review")
                if font_check and missing_fonts(page, [font_check]):
                    raise SystemExit(f"captions: the font {font_check} did not load (offline?); a fallback font fails review")
            shot = page.call("Page.captureScreenshot", format="png",
                             clip={"x": 0, "y": 0, "width": size[0], "height": size[1], "scale": 1})
            dst = out_dir / f"{key}.png"
            dst.write_bytes(base64.b64decode(shot["data"]))
            paths[key] = str(dst)
    return paths
