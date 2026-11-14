#!/usr/bin/env python3
"""Runs the pinned render engine (HyperFrames, see ../ENGINE.json): `engine.py <command> [args]`, e.g.
`engine.py check --json`. It puts a Node 22+ first on PATH when one is installed and runs npx with the pin, so the
version never floats. Works on Mac and Windows (no `sh`). Never run cloud render, publish or anything that spends
through it. Python 3.9+, stdlib only.
"""

from __future__ import annotations

import ntpath
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
import doctor  # noqa: E402
import pin as pin_file  # noqa: E402


class EngineError(ValueError):
    """The engine cannot start; the message says what to install."""


def engine_command(
    pin: str,
    args: Sequence[str],
    node: Optional[str],
    which: Callable[[str], Optional[str]] = shutil.which,
    path_env: Optional[str] = None,
    plat: Optional[str] = None,
) -> tuple:
    """``(command, env)`` that runs ``npx --yes hyperframes@<pin> <args>``. ``env`` holds only a PATH with the
    folder of ``node`` first (empty when no Node 22+ was found, so npx comes from the current PATH). EngineError,
    naming the install command, when there is no npx."""
    plat = plat or doctor.current_platform()
    path = os.environ.get("PATH", "") if path_env is None else path_env
    dirname = ntpath.dirname if doctor.is_windows(plat) else os.path.dirname
    env = {"PATH": dirname(node) + os.pathsep + path} if node else {}
    npx = which("npx")
    if not npx:
        raise EngineError(f"npx not found: install Node.js 22 with `{doctor.install_for(plat, 'node22')}` and open a new terminal")
    return [npx, "--yes", f"hyperframes@{pin}", *args], env


def main(argv: Optional[list] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        version = pin_file.engine_pin(pin_file.ENGINE_JSON)
        node = doctor.find_node22()
        if not node:
            raise EngineError(
                f"Node.js 22 or newer not found: install it with `{doctor.install_for(doctor.current_platform(), 'node22')}` "
                "and open a new terminal")
        path = os.environ.get("PATH", "")
        path = os.path.dirname(node) + os.pathsep + path
        cmd, env = engine_command(version, args, node, which=lambda name: shutil.which(name, path=path))
    except ValueError as err:  # EngineError is a ValueError, and so is a bad pin
        print(err, file=sys.stderr)
        return 1
    try:
        return subprocess.run(cmd, env={**os.environ, **env}).returncode
    except OSError as err:
        print(f"cannot run the render engine: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
