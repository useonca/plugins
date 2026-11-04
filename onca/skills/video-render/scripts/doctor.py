#!/usr/bin/env python3
"""Checks the founder's Mac for what the Onca plugin's video skills need, and compares plugin versions.

usage: python3 doctor.py check                     one line per check, with the install command when missing
       python3 doctor.py version                   this plugin's installed version
       python3 doctor.py check-update --latest X   current | outdated | newer | unknown
       python3 doctor.py node22                    the path of a Node 22+ binary, or nothing

It installs nothing: the skill shows the founder the install commands and runs them only after a yes.
Always exits 0; the answer is in what it prints. Python 3.9+, stdlib only.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import platform
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Optional

SEMVER = re.compile(r"(\d+)\.(\d+)\.(\d+)")
SKILL_DIR = Path(__file__).resolve().parent.parent
TOOLS = ("ffmpeg", "ffprobe", "uv", "parakeet-mlx", "scenedetect", "mlx_audio.tts.generate")
OPTIONAL = {"mlx_audio.tts.generate": "only for the voice skill"}
INSTALL = {
    "node22": "brew install node@22",
    "ffmpeg": "brew install ffmpeg",
    "ffprobe": "brew install ffmpeg",
    "uv": "brew install uv",
    "parakeet-mlx": "uv tool install parakeet-mlx",
    "scenedetect": "uv tool install scenedetect",
    "mlx_audio.tts.generate": "uv tool install mlx-audio",
}
NODE_MIN = 22


def _semver(value: Optional[str]) -> Optional[tuple]:
    match = SEMVER.fullmatch(value.strip()) if isinstance(value, str) else None
    return tuple(int(part) for part in match.groups()) if match else None


def compare_versions(installed: Optional[str], latest: Optional[str]) -> str:
    """``outdated`` when ``installed`` is older than ``latest``, ``current`` when equal, ``newer`` when ahead,
    ``unknown`` when either is missing or not x.y.z."""
    mine, theirs = _semver(installed), _semver(latest)
    if mine is None or theirs is None:
        return "unknown"
    if mine < theirs:
        return "outdated"
    return "current" if mine == theirs else "newer"


def own_version(skill_dir: Path) -> Optional[str]:
    """The plugin's version from its Claude Code manifest, else its portable one (two levels above the skill)."""
    root = Path(skill_dir).resolve().parent.parent
    for manifest in (root / ".claude-plugin" / "plugin.json", root / "plugin.json"):
        try:
            version = json.loads(manifest.read_text(encoding="utf-8")).get("version")
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(version, str):
            return version
    return None


def node_major(version: Optional[str]) -> Optional[int]:
    """22 for ``v22.3.0`` or ``22.3.0``; None for anything else."""
    match = re.match(r"v?(\d+)\.", version.strip()) if isinstance(version, str) else None
    return int(match.group(1)) if match else None


def _node_version(node: str) -> Optional[str]:
    try:
        return subprocess.run([node, "--version"], capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def _by_version(paths: list) -> list:
    def key(path: str) -> tuple:
        found = re.search(r"v?(\d+)(?:\.(\d+))?(?:\.(\d+))?", Path(path).parent.parent.name.replace("node@", ""))
        return tuple(int(g or 0) for g in found.groups()) if found else (0, 0, 0)
    return sorted(paths, key=key)


def find_node22(
    path_env: Optional[str] = None,
    home: Optional[Path] = None,
    version_of: Callable[[str], Optional[str]] = _node_version,
    brew_prefixes: tuple = ("/opt/homebrew", "/usr/local"),
) -> Optional[str]:
    """A Node 22+ binary: a ``node`` on PATH that is new enough, else Homebrew's newest ``node@22`` or later
    (keg-only, so not on PATH), else nvm's newest v22 or later. None when there is none."""
    path_env = os.environ.get("PATH", "") if path_env is None else path_env
    for folder in path_env.split(os.pathsep):
        node = os.path.join(folder, "node")
        if folder and os.access(node, os.X_OK) and (node_major(version_of(node)) or 0) >= NODE_MIN:
            return node
    kegs = [p for prefix in brew_prefixes for p in glob.glob(f"{prefix}/opt/node@*/bin/node")]
    home = Path.home() if home is None else Path(home)
    nvm = glob.glob(str(home / ".nvm" / "versions" / "node" / "v*" / "bin" / "node"))
    for group in (kegs, nvm):
        for node in reversed(_by_version(group)):
            if (node_major(version_of(node)) or 0) >= NODE_MIN:
                return node
    return None


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    install: Optional[str]


def checks(found: Mapping[str, Optional[str]], machine: str, node_version: Optional[str]) -> list:
    """Every check, in order: Apple Silicon, Node 22+, then each tool of ``TOOLS`` (``found`` maps a tool to its
    path or None)."""
    node_ok = (node_major(node_version) or 0) >= NODE_MIN
    out = [
        Check("apple_silicon", machine == "arm64",
              "Apple Silicon" if machine == "arm64" else f"{machine or 'unknown'}: transcription and voice need Apple Silicon",
              None),
        Check("node22", node_ok, f"node {node_version}" if node_version else "no Node.js found",
              None if node_ok else INSTALL["node22"]),
    ]
    for tool in TOOLS:
        path = found.get(tool)
        note = f" ({OPTIONAL[tool]})" if tool in OPTIONAL else ""
        out.append(Check(tool, path is not None, (path or "not found") + note, None if path else INSTALL[tool]))
    return out


def find_tool(name: str, path_env: Optional[str] = None, home: Optional[Path] = None) -> Optional[str]:
    """``name`` on PATH, else in ``~/.local/bin`` (where ``uv tool install`` puts it)."""
    found = shutil.which(name, path=os.environ.get("PATH", "") if path_env is None else path_env)
    if found:
        return found
    local = (Path.home() if home is None else Path(home)) / ".local" / "bin" / name
    return str(local) if os.access(local, os.X_OK) else None


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check")
    sub.add_parser("version")
    sub.add_parser("node22")
    update = sub.add_parser("check-update")
    update.add_argument("--latest", required=True)
    args = parser.parse_args(argv)
    if args.command == "version":
        print(own_version(SKILL_DIR) or "unknown")
    elif args.command == "check-update":
        print(compare_versions(own_version(SKILL_DIR), args.latest))
    elif args.command == "node22":
        print(find_node22() or "")
    else:
        node = find_node22()
        found = {tool: find_tool(tool) for tool in TOOLS}
        for check in checks(found, platform.machine(), _node_version(node) if node else None):
            status = "ok" if check.ok else ("optional" if check.name in OPTIONAL else "MISSING")
            line = f"{status} {check.name}: {check.detail}"
            print(line + (f"  install: {check.install}" if check.install else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
