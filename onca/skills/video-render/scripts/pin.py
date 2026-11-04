#!/usr/bin/env python3
"""The render engine's pinned version, from ../ENGINE.json. Run as a script it prints the pin."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SEMVER = re.compile(r"\d+\.\d+\.\d+")
ENGINE_JSON = Path(__file__).resolve().parent.parent / "ENGINE.json"


def engine_pin(engine_json: Path) -> str:
    """The ``version`` of ``engine_json``; ValueError when the file is missing or the version is not x.y.z."""
    try:
        version = json.loads(Path(engine_json).read_text(encoding="utf-8")).get("version")
    except (OSError, ValueError, AttributeError) as err:
        raise ValueError(f"cannot read the engine pin from {engine_json}: {type(err).__name__}") from err
    if not isinstance(version, str) or not SEMVER.fullmatch(version):
        raise ValueError(f"the engine pin in {engine_json} is not a version like 1.2.3: {version!r}")
    return version


if __name__ == "__main__":
    try:
        print(engine_pin(ENGINE_JSON))
    except ValueError as err:
        print(err, file=sys.stderr)
        sys.exit(1)
