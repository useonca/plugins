#!/usr/bin/env python3
"""Checks the founder's Mac or Windows PC for what the Onca plugin's video skills need, and compares plugin versions.

usage: doctor.py check                     one line per check, with the install command when missing
       doctor.py version                   this plugin's installed version
       doctor.py check-update --latest X   current | outdated | newer | unknown
       doctor.py node22                    the path of a Node 22+ binary, or nothing
       doctor.py python                    the Python command to use: python3, or "py -3 -X utf8" on Windows
(run it as `python3 doctor.py ...` on a Mac, `py -3 -X utf8 doctor.py ...` on Windows)

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
from typing import Callable, Mapping, Optional, Sequence

SEMVER = re.compile(r"(\d+)\.(\d+)\.(\d+)")
SKILL_DIR = Path(__file__).resolve().parent.parent
MAC_TOOLS = ("ffmpeg", "ffprobe", "uv", "parakeet-mlx", "scenedetect", "mlx_audio.tts.generate", "demucs-mlx")
OTHER_TOOLS = ("ffmpeg", "ffprobe", "uv", "whisper-ctranslate2", "scenedetect", "demucs")
ARM_WINDOWS_TOOLS = ("ffmpeg", "ffprobe", "uv", "scenedetect")
OPTIONAL = {
    "mlx_audio.tts.generate": "only for the voice skill",
    "demucs-mlx": "only for voice separation",
    "demucs": "only for voice separation",
    "docker": "only for the optional Docker render (render --docker)",
    "hw_encoder": "a computer with none still renders, on the CPU",
}
INSTALL = {
    "node22": "brew install node@22",
    "ffmpeg": "brew install ffmpeg",
    "ffprobe": "brew install ffmpeg",
    "uv": "brew install uv",
    "parakeet-mlx": "uv tool install parakeet-mlx",
    "scenedetect": "uv tool install scenedetect",
    "mlx_audio.tts.generate": "uv tool install mlx-audio",
    "demucs-mlx": "uv tool install demucs-mlx",
    "docker": "brew install --cask docker",
}
WINDOWS_INSTALL = {
    "node22": "winget install OpenJS.NodeJS.22",
    "ffmpeg": "winget install Gyan.FFmpeg",
    "ffprobe": "winget install Gyan.FFmpeg",
    "uv": "winget install --id=astral-sh.uv -e",
    "whisper-ctranslate2": "uv tool install whisper-ctranslate2",
    "scenedetect": "uv tool install scenedetect",
    "demucs": "uv tool install demucs",
    "docker": "winget install Docker.DockerDesktop",
}
HW_NOTE = "no hardware encoder: renders use the CPU (libx264), which works but is slower"
NODE_MIN = 22


def detect_platform(system: str, machine: str) -> str:
    """``mac-arm``, ``mac-intel``, ``windows`` (x64), ``windows-arm`` or ``linux``, from ``platform.system()`` and
    ``platform.machine()``."""
    machine = (machine or "").lower()
    if system == "Darwin":
        return "mac-arm" if machine in ("arm64", "aarch64") else "mac-intel"
    if system == "Windows":
        return "windows-arm" if machine in ("arm64", "aarch64") else "windows"
    return "linux"


def current_platform() -> str:
    return detect_platform(platform.system(), platform.machine())


def is_windows(plat: Optional[str]) -> bool:
    return (plat or current_platform()).startswith("windows")


def tools_for(plat: str) -> tuple:
    """The tools to look for on this platform, in the order the check lists them."""
    if plat == "mac-arm":
        return MAC_TOOLS
    return ARM_WINDOWS_TOOLS if plat == "windows-arm" else OTHER_TOOLS


def install_for(plat: str, tool: str) -> str:
    """The command that installs ``tool`` on ``plat`` (shown to the founder; run only after their yes)."""
    if plat.startswith("windows"):
        return WINDOWS_INSTALL.get(tool, f"uv tool install {tool}")
    if plat.startswith("mac"):
        return INSTALL.get(tool, f"uv tool install {tool}")
    return {
        "node22": "install Node.js 22 or later from https://nodejs.org",
        "ffmpeg": "install ffmpeg with your package manager", "ffprobe": "install ffmpeg with your package manager",
        "uv": "install uv from https://docs.astral.sh/uv/", "docker": "install Docker from https://docs.docker.com/engine/install/",
    }.get(tool, f"uv tool install {tool}")


def python_command(plat: Optional[str] = None) -> str:
    """The command that runs a plugin script: ``py -3 -X utf8`` on Windows (the launcher; -X utf8 keeps console
    output readable on a cp1252 pipe), ``python3`` elsewhere."""
    return "py -3 -X utf8" if is_windows(plat) else "python3"


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
        return subprocess.run([node, "--version"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def _by_version(paths: list) -> list:
    def key(path: str) -> tuple:
        found = re.search(r"v?(\d+)(?:\.(\d+))?(?:\.(\d+))?", Path(path).parent.parent.name.replace("node@", ""))
        return tuple(int(g or 0) for g in found.groups()) if found else (0, 0, 0)
    return sorted(paths, key=key)


def _node_windows(path_env: str, env: Mapping[str, str]) -> list:
    """Windows places a Node.js may be, in the order to try: PATH, the installer's folders, nvm-windows."""
    out = [os.path.join(folder, "node.exe") for folder in path_env.split(os.pathsep) if folder]
    for var, sub in (("ProgramFiles", "nodejs"), ("LOCALAPPDATA", os.path.join("Programs", "nodejs"))):
        if env.get(var):
            out.append(os.path.join(env[var], sub, "node.exe"))
    if env.get("NVM_HOME"):
        out.extend(sorted(glob.glob(os.path.join(env["NVM_HOME"], "v*", "node.exe")), key=_vkey, reverse=True))
    return out


def _vkey(path: str) -> tuple:
    found = re.search(r"v?(\d+)(?:\.(\d+))?(?:\.(\d+))?", Path(path).parent.name)
    return tuple(int(g or 0) for g in found.groups()) if found else (0, 0, 0)


def find_node22(
    path_env: Optional[str] = None,
    home: Optional[Path] = None,
    version_of: Callable[[str], Optional[str]] = _node_version,
    brew_prefixes: tuple = ("/opt/homebrew", "/usr/local"),
    plat: Optional[str] = None,
    env: Optional[Mapping[str, str]] = None,
) -> Optional[str]:
    """A Node 22+ binary: a ``node`` on PATH that is new enough, else (Mac) Homebrew's newest ``node@22`` or later
    (keg-only, so not on PATH), else nvm's newest v22 or later; on Windows the installer's folders
    (``%ProgramFiles%\\nodejs``, ``%LOCALAPPDATA%\\Programs\\nodejs``) and nvm-windows. None when there is none."""
    path_env = os.environ.get("PATH", "") if path_env is None else path_env
    env = os.environ if env is None else env
    if is_windows(plat):
        for node in _node_windows(path_env, env):
            if os.path.isfile(node) and (node_major(version_of(node)) or 0) >= NODE_MIN:
                return node
        return None
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


def hw_candidates(plat: str) -> tuple:
    """The hardware H.264 encoders worth trying on this platform."""
    if plat == "mac-arm":
        return ("h264_videotoolbox",)
    if plat in ("windows", "linux"):
        return ("h264_nvenc", "h264_qsv", "h264_amf")
    return ()


def probe_command(ffmpeg: str, encoder: str, size: str = "1080x1920") -> list:
    """A one-frame trial encode with ``encoder`` to nowhere: exit 0 means this machine can use it (an encoder that
    ffmpeg lists can still fail when the GPU or driver is missing)."""
    return [ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c=black:s={size}:d=0.1",
            "-frames:v", "1", "-c:v", encoder, "-pix_fmt", "yuv420p", "-f", "null", "-"]


def _exit_code(cmd: list) -> int:
    try:
        return subprocess.run(cmd, capture_output=True, timeout=30).returncode
    except (OSError, subprocess.SubprocessError):
        return 1


def probe_hw(ffmpeg: str, plat: str, run: Callable[[list], int] = _exit_code,
             candidates: Optional[Sequence[str]] = None) -> dict:
    """Each hardware encoder (``hw_candidates(plat)``, or ``candidates``) -> whether a trial encode worked."""
    return {enc: run(probe_command(ffmpeg, enc)) == 0 for enc in (hw_candidates(plat) if candidates is None else candidates)}


def checks(found: Mapping[str, Optional[str]], plat: str, node_version: Optional[str],
           hw: Optional[Mapping[str, bool]] = None) -> list:
    """Every check, in order: platform, Node 22+, each tool of ``tools_for(plat)`` (``found`` maps a tool to its
    path or None), the optional ``docker`` when ``found`` has the key, then the hardware encoder when ``hw`` is given."""
    node_ok = (node_major(node_version) or 0) >= NODE_MIN
    arm_windows = plat == "windows-arm"
    out = [
        Check("platform", not arm_windows,
              "windows-arm: local transcription and voice need an x64 Windows" if arm_windows else plat, None),
        Check("node22", node_ok, f"node {node_version}" if node_version else "no Node.js found",
              None if node_ok else install_for(plat, "node22")),
    ]
    names = list(tools_for(plat)) + (["docker"] if "docker" in found else [])
    for tool in names:
        path = found.get(tool)
        note = f" ({OPTIONAL[tool]})" if tool in OPTIONAL else ""
        out.append(Check(tool, path is not None, (path or "not found") + note, None if path else install_for(plat, tool)))
    if hw is not None:
        names = ", ".join(f"{enc} {'ok' if ok else 'no'}" for enc, ok in hw.items())
        out.append(Check("hw_encoder", any(hw.values()), names if any(hw.values()) else HW_NOTE, None))
    return out


def find_tool(name: str, path_env: Optional[str] = None, home: Optional[Path] = None,
              env: Optional[Mapping[str, str]] = None, plat: Optional[str] = None) -> Optional[str]:
    """``name`` on PATH (Windows: with PATHEXT), else in ``~/.local/bin`` (where ``uv tool install`` puts it, as
    ``name.exe`` on Windows), else (Windows) winget's link folder and ffmpeg's package folder. None when missing."""
    path_env = os.environ.get("PATH", "") if path_env is None else path_env
    found = shutil.which(name, path=path_env)
    if found:
        return found
    local = (Path.home() if home is None else Path(home)) / ".local" / "bin"
    if not is_windows(plat):
        candidate = local / name
        return str(candidate) if os.access(candidate, os.X_OK) else None
    env = os.environ if env is None else env
    places = [str(local / name), str(local / f"{name}.exe")]
    if env.get("LOCALAPPDATA"):
        winget = os.path.join(env["LOCALAPPDATA"], "Microsoft", "WinGet")
        places.append(os.path.join(winget, "Links", f"{name}.exe"))
        places.extend(sorted(glob.glob(os.path.join(winget, "Packages", "Gyan.FFmpeg*", "*", "bin", f"{name}.exe"))))
        places.extend(sorted(glob.glob(os.path.join(winget, "Packages", "*", f"{name}.exe"))))
    return next((p for p in places if os.path.isfile(p)), None)


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check")
    sub.add_parser("version")
    sub.add_parser("node22")
    sub.add_parser("python")
    update = sub.add_parser("check-update")
    update.add_argument("--latest", required=True)
    args = parser.parse_args(argv)
    if args.command == "version":
        print(own_version(SKILL_DIR) or "unknown")
    elif args.command == "check-update":
        print(compare_versions(own_version(SKILL_DIR), args.latest))
    elif args.command == "node22":
        print(find_node22() or "")
    elif args.command == "python":
        print(python_command())
    else:
        plat = current_platform()
        node = find_node22()
        found = {tool: find_tool(tool) for tool in (*tools_for(plat), "docker")}
        ffmpeg = found.get("ffmpeg")
        hw = probe_hw(ffmpeg, plat) if ffmpeg else None
        for check in checks(found, plat, _node_version(node) if node else None, hw):
            status = "ok" if check.ok else ("optional" if check.name in OPTIONAL else "MISSING")
            line = f"{status} {check.name}: {check.detail}"
            print(line + (f"  install: {check.install}" if check.install else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
