"""What the screen-demo and b-roll command lines share: the video-edit shell (ffmpeg, ffprobe, logs, contact
sheets), the pinned render engine, the finish to the render contract and the exit codes (2 bad input, one
problem per line; 1 a failed tool)."""

from __future__ import annotations

import sys
from pathlib import Path

_EDIT = Path(__file__).resolve().parents[2] / "video-edit" / "scripts"
sys.path.insert(0, str(_EDIT))
import captions  # noqa: E402
import core  # noqa: E402
import shell  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
import flow_core  # noqa: E402

hf = captions.hf
log = shell.log
run = shell.run
probe = shell.probe
fonts_loaded = shell.fonts_loaded


def bad_input(problems) -> None:
    """Exit 2 with one problem per line."""
    for p in problems if isinstance(problems, (list, tuple)) else str(problems).split("; "):
        print(p, file=sys.stderr)
    raise SystemExit(2)


def parse_size(text: str) -> tuple[int, int]:
    size = flow_core.parse_size(text)
    if not size:
        bad_input([f"size must be WIDTHxHEIGHT, like 1920x1080, not {text!r}"])
    return size


def render(project: Path, out: Path, draft: bool) -> None:
    """`check` (its JSON kept in check.json), then a render of the project to `out`."""
    check = hf(project, "check", "--json", check=False)
    (project / "check.json").write_text(check.stdout, encoding="utf-8")
    if check.returncode != 0:
        log("the render check reported problems; see check.json (rendering anyway, judge from the frames)")
    hf(project, "render", "--quality", "draft" if draft else "delivery", "--output", str(Path(out).resolve()))


# The render contract's video encode (H.264, yuv420p, 30 fps); every finished clip goes through it.
VIDEO = ["-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", "-r", "30"]
LUFS = -16.0


def finish(src: Path, dst: Path, sound: bool) -> None:
    """The render contract: H.264, yuv420p, 30 fps, faststart; with sound, loudness -16 LUFS measured first and
    applied in a second pass, as video-edit's render does."""
    audio = ["-an"]
    if sound:
        m = core.parse_loudnorm(shell.ffmpeg_log(["-i", str(src), "-vn", "-af", f"loudnorm=I={LUFS}:TP=-1.5:LRA=11:print_format=json"]))
        audio = ["-af", core.loudnorm_apply(m, LUFS) + ",aresample=48000", "-c:a", "aac", "-b:a", "192k"]
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), *VIDEO, *audio, "-movflags", "+faststart", str(dst)])


def contact(video: Path, duration: float) -> Path:
    """A contact sheet of about 14 frames next to the video: NAME-contact.png."""
    sheet = Path(video).with_name(Path(video).stem + "-contact.png")
    shell.contact_sheet(video, core.sheet_times(duration), sheet)
    return sheet
