"""A recipe: a reference video broken into its style, pacing and beats, each beat naming the parts that build
it. Pure: validation and the cues skeleton the client fills in."""

from __future__ import annotations

import json

import kit_core

ASPECTS = {"9:16": [1080, 1920], "16:9": [1920, 1080], "1:1": [1080, 1080], "4:5": [1080, 1350]}
SECTIONS = ("pace", "look", "sound")
# Params a part cannot play without, as placeholders the client replaces.
PLACEHOLDERS = {"odometer": {"to": 100}, "chart": {"values": [1, 2, 3]},
                "morph": {"states": [{"at": 0, "w": 200, "h": 200, "radius": 40}, {"at": 0.6, "w": 600, "h": 160, "radius": 80}]}}


def validate(recipe) -> list:
    """Every problem with a recipe.json, all at once."""
    if not isinstance(recipe, dict):
        return ["recipe.json must be a JSON object"]
    problems = []
    if recipe.get("version") != 1:
        problems.append(f"version must be 1, got {recipe.get('version')!r}")
    if not isinstance(recipe.get("source"), str) or not recipe.get("source"):
        problems.append("source must name the reference video")
    duration = recipe.get("duration")
    if not kit_core._num(duration) or duration <= 0:
        problems.append(f"duration must be seconds over 0, got {duration!r}")
    if recipe.get("aspect") not in ASPECTS:
        problems.append(f"aspect must be one of {', '.join(ASPECTS)}, got {recipe.get('aspect')!r}")
    for key in SECTIONS:
        if not isinstance(recipe.get(key), dict):
            problems.append(f"{key} must be an object")
    beats = recipe.get("beats")
    if not isinstance(beats, list) or not beats:
        return problems + ["beats must list the video's beats (at least one)"]
    last = 0.0
    for k, b in enumerate(beats):
        if not isinstance(b, dict):
            problems.append(f"beats[{k}] must be an object")
            continue
        a, z = b.get("from"), b.get("to")
        if not (kit_core._num(a) and kit_core._num(z) and 0 <= a < z):
            problems.append(f"beats[{k}]: needs from < to, in seconds")
        elif a < last - 1e-9:
            problems.append(f"beats[{k}]: starts at {a:g}, before the beat ahead of it ends")
        else:
            last = z
        if not isinstance(b.get("says"), str):
            problems.append(f"beats[{k}]: says must be text (what the beat says, or \"\")")
        parts = b.get("parts")
        if not isinstance(parts, list) or not parts:
            problems.append(f"beats[{k}]: parts must list one or more motion parts")
        else:
            for name in parts:
                if name not in kit_core.PARTS:
                    problems.append(f"beats[{k}]: unknown part {name!r}")
    return problems


def skeleton(recipe: dict) -> dict:
    """A cues doc with one cue per listed part (`{part}-{n}`), each at its beat's start, in time order. The
    client then gives each cue its element in index.html, its params and its timing."""
    problems = validate(recipe)
    if problems:
        raise ValueError("; ".join(problems))
    seen, cues = {}, []
    for b in recipe["beats"]:
        for part in b["parts"]:
            seen[part] = seen.get(part, 0) + 1
            cues.append({"id": f"{part}-{seen[part]}", "part": part, "at": b["from"],
                         "params": json.loads(json.dumps(PLACEHOLDERS.get(part, {})))})
    cues.sort(key=lambda c: c["at"])
    return {"version": 1, "fps": 30, "size": list(ASPECTS[recipe["aspect"]]), "duration": recipe["duration"],
            "cues": cues}
