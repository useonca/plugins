#!/usr/bin/env python3
"""Read a product's real colours, fonts and copy from its source, so a rebuilt screen uses only those (rung 1).

usage: tokens.py SRC --out tokens.json

It only reads: Xcode colour sets, Swift `Color(...)` constants, CSS custom properties, CSS `font-family`
and Swift `.custom("Name"` fonts, the family names of bundled font files (.ttf, .otf, .woff, .woff2),
`.xcstrings` and `.strings` copy. It skips .git, node_modules, .build,
build and DerivedData, and writes nothing but `--out`:
{"colors": {name: value}, "fonts": [names], "copy": {key: text}, "files": [paths read]}.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", ".build", "build", "DerivedData", ".next", "dist", "venv", ".venv", "Pods"}
MAX_BYTES = 2_000_000
GENERIC_FONTS = {
    "serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui", "ui-sans-serif", "ui-serif",
    "ui-monospace", "ui-rounded", "-apple-system", "blinkmacsystemfont", "emoji", "math", "fangsong",
    "inherit", "initial", "unset", "revert", "apple color emoji", "segoe ui emoji", "segoe ui symbol",
    "noto color emoji",
}
FONT_FILES = (".ttf", ".otf", ".woff", ".woff2")
COLOR_VALUE = re.compile(r"^(#[0-9a-fA-F]{3,8}|(rgb|rgba|hsl|hsla|oklch|oklab|lab|lch|color)\(.*\))$")


def _hex(r: float, g: float, b: float) -> str:
    return "#" + "".join(f"{max(0, min(255, int(v * 255 + 0.5))):02X}" for v in (r, g, b))


def _component(v) -> tuple[float, bool] | None:
    """(value, is_integer_form) of a colour component."""
    if isinstance(v, bool):
        return None
    if isinstance(v, float):
        return v, False
    if isinstance(v, int):
        return float(v), True
    if isinstance(v, str):
        s = v.strip()
        try:
            if s.lower().startswith("0x"):
                return int(s, 16) / 255, False
            if "." in s:
                return float(s), False
            return float(int(s)), True
        except ValueError:
            return None
    return None


def colorset(doc: dict) -> str | None:
    """`#RRGGBB` of an Xcode colour set: its universal entry, else its light one."""
    entries = doc.get("colors") if isinstance(doc, dict) else None
    if not entries:
        return None

    def is_dark(e):
        return any(a.get("value") == "dark" for a in e.get("appearances", []) if isinstance(a, dict))

    entry = next((e for e in entries if not is_dark(e) and not e.get("appearances")), None)
    entry = entry or next((e for e in entries if not is_dark(e)), None)
    comps = (entry or {}).get("color", {}).get("components")
    if not isinstance(comps, dict):
        return None
    parts = [_component(comps.get(k)) for k in ("red", "green", "blue")]
    if any(p is None for p in parts):
        return None
    ints = [v for v, is_int in parts if is_int]
    eight_bit = bool(ints) and max(ints) > 1
    vals = [v / 255 if is_int and eight_bit else v for v, is_int in parts]
    return _hex(*vals)


def _num(expr: str) -> float | None:
    """A number or one division (`128/255`, `0.5`)."""
    m = re.fullmatch(r"\s*([\d.]+)\s*(?:/\s*([\d.]+)\s*)?", expr)
    if not m:
        return None
    try:
        v = float(m.group(1))
        return v / float(m.group(2)) if m.group(2) else v
    except (ValueError, ZeroDivisionError):
        return None


_SWIFT_COLOR = re.compile(r"static\s+(?:let|var)\s+(\w+)\s*(?::\s*[\w.]+\s*)?=\s*(?:SwiftUI\.)?Color\s*\(([^()]*(?:\([^()]*\)[^()]*)*)\)")


def swift_colors(text: str) -> dict[str, str]:
    """`static let name = Color(red:green:blue:)`, `Color(hex: "...")` and `Color(.sRGB, red: ...)` as hex."""
    out = {}
    for name, args in _SWIFT_COLOR.findall(text):
        m = re.search(r'hex:\s*"#?([0-9a-fA-F]{6})"', args)
        if m:
            out[name] = "#" + m.group(1).upper()
            continue
        parts = {}
        for key in ("red", "green", "blue"):
            km = re.search(rf"\b{key}:\s*([\d./ ]+)", args)
            parts[key] = _num(km.group(1)) if km else None
        if all(v is not None for v in parts.values()):
            vals = [parts[k] for k in ("red", "green", "blue")]
            if max(vals) > 1:
                vals = [v / 255 for v in vals]
            out[name] = _hex(*vals)
    return out


def css_vars(text: str) -> dict[str, str]:
    """Every CSS custom property `--name: value`, last value wins."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return {m.group(1): m.group(2).strip() for m in re.finditer(r"--([\w-]+)\s*:\s*([^;{}]+)", text)}


def fonts(text: str) -> list[str]:
    """Font family names in first-seen order: CSS `font-family` lists and Swift `.custom("Name"`."""
    found = []
    for m in re.finditer(r"font-family\s*:\s*([^;}\n]+)", text):
        for name in m.group(1).split(","):
            found.append((m.start(), name.strip().strip("'\"").strip()))
    for m in re.finditer(r'\.custom\(\s*"([^"]+)"', text):
        found.append((m.start(), m.group(1)))
    out = []
    for _, name in sorted(found, key=lambda p: p[0]):
        if name and name.lower() not in GENERIC_FONTS and not name.startswith("var(") and name not in out:
            out.append(name)
    return out


def xcstrings(text: str, lang: str = "en") -> dict[str, str]:
    """The `lang` value of each key of a String Catalog; a key with no entry in its own source language is
    its own text."""
    doc = json.loads(text)
    source = doc.get("sourceLanguage", "en")
    out = {}
    for key, entry in (doc.get("strings") or {}).items():
        unit = ((entry or {}).get("localizations", {}).get(lang) or {}).get("stringUnit") or {}
        if isinstance(unit.get("value"), str):
            out[key] = unit["value"]
        elif lang == source:
            out[key] = key
    return out


def _unescape(s: str) -> str:
    return re.sub(r'\\(["\\n t])', lambda m: {"n": "\n", "t": "\t"}.get(m.group(1), m.group(1)), s)


def strings_file(text: str) -> dict[str, str]:
    """`"key" = "value";` pairs of a `.strings` file, comments skipped."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"(?m)^\s*//.*$", "", text)
    pat = re.compile(r'"((?:[^"\\]|\\.)*)"\s*=\s*"((?:[^"\\]|\\.)*)"\s*;')
    return {_unescape(k): _unescape(v) for k, v in pat.findall(text)}


def scan(src: Path) -> dict:
    colors: dict[str, str] = {}
    font_list: list[str] = []
    copy: dict[str, str] = {}
    files: list[str] = []
    for root, dirs, names in os.walk(src):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(names):
            path = Path(root) / name
            suffix = path.suffix.lower()
            in_colorset = path.parent.suffix == ".colorset" and name == "Contents.json"
            if suffix in FONT_FILES:
                family = path.stem.split("-")[0]
                if family and family not in font_list:
                    font_list.append(family)
                files.append(str(path.relative_to(src)))
                continue
            if not (in_colorset or suffix in (".swift", ".css", ".scss", ".sass", ".less", ".xcstrings", ".strings")):
                continue
            try:
                if path.stat().st_size > MAX_BYTES:
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            files.append(str(path.relative_to(src)))
            try:
                if in_colorset:
                    value = colorset(json.loads(text))
                    if value:
                        colors[path.parent.stem] = value
                elif suffix == ".swift":
                    colors.update(swift_colors(text))
                    font_list += [f for f in fonts(text) if f not in font_list]
                elif suffix == ".xcstrings":
                    copy.update(xcstrings(text))
                elif suffix == ".strings":
                    copy.update(strings_file(text))
                else:
                    colors.update({k: v for k, v in css_vars(text).items() if COLOR_VALUE.match(v)})
                    font_list += [f for f in fonts(text) if f not in font_list]
            except ValueError as e:
                print(f"[screen-demo] skipped {path.relative_to(src)}: {e}", file=sys.stderr)
    return {"colors": colors, "fonts": font_list, "copy": copy, "files": files}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Read a product's colours, fonts and copy from its source (read only).")
    ap.add_argument("src", help="the product's source folder")
    ap.add_argument("--out", required=True, help="tokens.json to write")
    a = ap.parse_args(argv)
    src = Path(a.src)
    if not src.is_dir():
        print(f"not a folder: {src}", file=sys.stderr)
        raise SystemExit(2)
    doc = scan(src)
    Path(a.out).write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[screen-demo] {len(doc['colors'])} colours, {len(doc['fonts'])} fonts, {len(doc['copy'])} strings "
          f"from {len(doc['files'])} files -> {a.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
