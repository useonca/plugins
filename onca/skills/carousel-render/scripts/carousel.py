"""Carousel slides from one HyperFrames composition (stdlib, Python 3.9).

    python3 carousel.py times SLIDES
        The snapshot times of SLIDES one-second scenes: 0.5,1.5,... (pass them to `snapshot --at`).
    python3 carousel.py collect PROJECT OUT NAME --slides N [--size 1080x1350]
        Copies the newest snapshot run's frames at those times, in order, to OUT/NAME-01.png onward and checks
        each PNG's size from its header. Exit 1 when a slide's frame is missing or a size is wrong.

The snapshot run writes its PNGs under PROJECT/.hyperframes/artifacts/snapshots/<run>/frame-NN-at-<t>s.png (plus
a closing frame, which is not a slide); the newest run folder is the one collected.
"""

import argparse
import re
import shutil
import struct
import sys
from pathlib import Path
from typing import List, Optional, Tuple

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
FRAME_RE = re.compile(r"frame-\d+-at-(\d+(?:\.\d+)?)s\.png")
SNAPSHOTS = Path(".hyperframes") / "artifacts" / "snapshots"


def times(slides: int) -> List[str]:
    """The middle of each one-second scene: '0.5', '1.5', ..."""
    return [f"{n}.5" for n in range(slides)]


def png_size(data: bytes) -> Optional[Tuple[int, int]]:
    """(width, height) from a PNG header, or None for anything else."""
    if len(data) < 24 or not data.startswith(PNG_SIGNATURE):
        return None
    return struct.unpack(">II", data[16:24])


def newest_run(project: Path) -> Optional[Path]:
    """The snapshot run folder modified last (a folder holding frames directly counts as the run)."""
    root = project / SNAPSHOTS
    if any(FRAME_RE.fullmatch(p.name) for p in project.glob("*.png")):
        return project
    runs = [p for p in root.iterdir() if p.is_dir()] if root.is_dir() else []
    return max(runs, key=lambda p: (p.stat().st_mtime, p.name)) if runs else None


def frames_at(run: Path) -> dict:
    """{time in seconds: frame path} of a run's frames."""
    found = {}
    for path in run.glob("*.png"):
        match = FRAME_RE.fullmatch(path.name)
        if match:
            found[round(float(match.group(1)), 3)] = path
    return found


def collect(project: Path, out: Path, name: str, slides: int, size: Tuple[int, int]) -> Tuple[List[Path], List[str]]:
    """The slides copied in order and the problems (a missing frame, a wrong size); nothing is copied on a problem."""
    run = newest_run(project)
    if run is None:
        return [], [f"no snapshot run in {project / SNAPSHOTS}: run the engine's snapshot first"]
    found = frames_at(run)
    picks, problems = [], []
    for n, at in enumerate(times(slides), start=1):
        path = found.get(round(float(at), 3))
        if path is None:
            problems.append(f"slide {n}: no frame at {at}s in {run}")
            continue
        got = png_size(path.read_bytes())
        if got is None:
            problems.append(f"slide {n}: {path.name} is not a PNG")
        elif got != size:
            problems.append(f"slide {n}: {path.name} is {got[0]}x{got[1]}, not {size[0]}x{size[1]}")
        picks.append(path)
    if problems:
        return [], problems
    out.mkdir(parents=True, exist_ok=True)
    copied = []
    for n, path in enumerate(picks, start=1):
        target = out / f"{name}-{n:02d}.png"
        shutil.copyfile(path, target)
        copied.append(target)
    return copied, []


def _size(text: str) -> Tuple[int, int]:
    match = re.fullmatch(r"(\d+)x(\d+)", text)
    if not match:
        raise argparse.ArgumentTypeError("size is WIDTHxHEIGHT, e.g. 1080x1350")
    return int(match.group(1)), int(match.group(2))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Carousel slides from one HyperFrames composition.")
    sub = parser.add_subparsers(dest="command", required=True)
    t = sub.add_parser("times", help="the snapshot times of N one-second slides")
    t.add_argument("slides", type=int)
    c = sub.add_parser("collect", help="copy the newest snapshot run's slides to OUT/NAME-01.png onward")
    c.add_argument("project", type=Path)
    c.add_argument("out", type=Path)
    c.add_argument("name")
    c.add_argument("--slides", type=int, required=True)
    c.add_argument("--size", type=_size, default=(1080, 1350))
    args = parser.parse_args(argv)
    if args.command == "times":
        if args.slides < 1:
            parser.error("slides must be 1 or more")
        print(",".join(times(args.slides)))
        return 0
    copied, problems = collect(args.project, args.out, args.name, args.slides, args.size)
    for problem in problems:
        print(problem, file=sys.stderr)
    for path in copied:
        print(path)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
