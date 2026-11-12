"""Who does each step of an edit: Onca's free local tools by default, or another free program.

providers.json maps a step to a provider:
  local    the built-in tool (speech to text, the voice skill, voice separation, the encoder)
  command  a free local program: `argv` with {in}, {out} and {out_dir}, run without a shell
  file     a result the client already has (from an Onca service through Onca's tools, say): `path`

There is no network kind: these scripts hold no keys and never pay for anything. A known paid CLI is refused.
Pure: no files, no subprocesses (shell.run_provider runs a command).
"""

from __future__ import annotations

import re
from pathlib import PurePath

import core
import timeline_core as tlc

STEPS = ("transcribe", "voice", "separate", "encode")
KINDS = ("local", "command", "file")
FORMATS = {"transcribe": "words", "voice": "wav", "separate": "stems", "encode": None}
PAID_CLIS = {"higgsfield", "hf", "higgs", "elevenlabs", "heygen", "openai"}
LOCAL_ENCODERS = ("auto", *tlc.ENCODERS)
PLACEHOLDER = re.compile(r"\{(\w+)\}")


def validate(config: dict) -> list:
    """Every problem with a providers.json, all at once."""
    if not isinstance(config, dict):
        return ["providers.json is a JSON object of step -> provider"]
    problems = []
    for step, spec in config.items():
        if step not in STEPS:
            problems.append(f"{step}: not a step (steps: {', '.join(STEPS)})")
            continue
        if not isinstance(spec, dict):
            problems.append(f"{step}: a provider is an object with a kind")
            continue
        kind = spec.get("kind")
        if kind not in KINDS:
            problems.append(f"{step}: kind {kind!r} is not one of {', '.join(KINDS)} (no network kind: scripts make no paid calls)")
        elif kind == "command":
            argv = spec.get("argv")
            if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
                problems.append(f"{step}: a command needs `argv`, a list of strings")
            else:
                name = paid_cli(argv)
                if name:
                    problems.append(f"{step}: {name} is a paid service; run it only through Onca's approval, then hand its result in as a file")
        elif kind == "file":
            if not isinstance(spec.get("path"), str) or not spec["path"]:
                problems.append(f"{step}: a file provider needs `path`")
        if step == "encode" and kind in ("command", "file"):
            problems.append("encode: only the local encoder renders (name: " + ", ".join(LOCAL_ENCODERS) + ")")
        elif kind == "local" and step == "encode" and spec.get("name", "auto") not in LOCAL_ENCODERS:
            problems.append(f"encode: name {spec.get('name')!r} is not one of {', '.join(LOCAL_ENCODERS)}")
    return problems


def paid_cli(argv: list) -> str | None:
    """The paid service a command would run: the program itself (`/opt/bin/heygen`), or a command name anywhere
    after a launcher (`npx higgsfield`, `sh -c "elevenlabs ..."`); else None. A path argument (`/models/hf`) is
    data, not a command."""
    names = [PurePath(argv[0]).name] + [w for arg in argv[1:] for w in arg.split() if "/" not in w]
    for name in names:
        name = name.strip("'\"").lower().split("@")[0]
        if name in PAID_CLIS:
            return name
    return None


def resolve(step: str, config: dict | None) -> dict:
    """The provider for a step: {"step", "kind", ...}; local when the config has none. ValueError on problems."""
    if step not in STEPS:
        raise ValueError(f"unknown step {step}")
    if config:
        problems = validate(config)
        if problems:
            raise ValueError("; ".join(problems))
    spec = dict((config or {}).get(step) or {"kind": "local"})
    return {"step": step, **spec}


def command_argv(spec: dict, values: dict) -> list:
    """argv with {in}, {out}, {out_dir} filled in. ValueError on an unknown placeholder or a missing value."""
    out = []
    for arg in spec["argv"]:
        def fill(m):
            key = m.group(1)
            if key not in ("in", "out", "out_dir"):
                raise ValueError(f"unknown placeholder {{{key}}} (use {{in}}, {{out}}, {{out_dir}})")
            if key not in values:
                raise ValueError(f"no value for {{{key}}} in this step")
            return str(values[key])
        out.append(PLACEHOLDER.sub(fill, arg))
    return out


def describe(spec: dict) -> str:
    """One log line naming the provider."""
    if spec["kind"] == "command":
        return f"command {' '.join(spec['argv'])}"
    if spec["kind"] == "file":
        return f"file {spec['path']}"
    return "local" + (f" {spec['name']}" if spec.get("name") else "")


def _sec(w: dict, key: str):
    if f"{key}_ms" in w:
        return float(w[f"{key}_ms"]) / 1000
    return float(w[key])


def normalize_words(doc) -> list:
    """Words from any provider -> [{"i", "text", "start", "end"}] in seconds, sorted by start.
    Takes parakeet or whisper JSON, a list of words, or {"words": [...]}; a word has `text` or `word`, and `start`/`end`
    in seconds or `start_ms`/`end_ms`. ValueError for anything else."""
    if isinstance(doc, dict) and ("sentences" in doc or "segments" in doc):
        return core.words_from_asr(doc)
    items = doc.get("words") if isinstance(doc, dict) else doc
    if not isinstance(items, list):
        raise ValueError("words must be a list, {\"words\": [...]} or parakeet JSON")
    out = []
    for k, w in enumerate(items):
        try:
            text = w.get("text", w.get("word"))
            start, end = _sec(w, "start"), _sec(w, "end")
        except (AttributeError, KeyError, TypeError, ValueError):
            raise ValueError(f"word {k} needs text and start/end times") from None
        if not isinstance(text, str) or not text.strip() or end < start or start < 0:
            raise ValueError(f"word {k} is not a word with start <= end: {w!r}")
        out.append({"text": text.strip(), "start": round(start, 3), "end": round(end, 3)})
    out.sort(key=lambda w: w["start"])
    return [{"i": i, **w} for i, w in enumerate(out)]
