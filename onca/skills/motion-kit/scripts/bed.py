"""A video's music bed made from code (free, own work, an exact bar grid), as a 48 kHz stereo 16-bit WAV.

usage: bed.py PLAN.json --out music/bed.wav

PLAN: {"bpm": 100, "key": "A", "chords": ["Am", "F", "C", "G"], "sections": [{"bars": 2, "kind": "intro"}, ...],
       "stops": [12.0], "end_ring": true}
Section kinds: intro (pad only), build (pad, pulse bass, hats, a riser into the next section), drop (full: kick,
clap, bass, arp), break (pad and arp, no drums), outro (pad and a last chord that rings). A "stop" mutes
everything but the pad for one beat ending at that time, so a click can land on the return. kit.py bed writes
the plan and runs this with uv and a pinned numpy. Exit 0 done, 2 a bad plan (every problem), 1 a write failure.
"""

from __future__ import annotations

import argparse
import json
import sys
import wave
from pathlib import Path

import numpy as np

SR = 48000
NOTES = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}
rng = np.random.default_rng(7)


def freq(semitone_from_a4: float) -> float:
    return 440.0 * 2 ** (semitone_from_a4 / 12)


def chord_notes(name: str, octave: int = 3) -> list[float]:
    minor = name.endswith("m")
    root = NOTES[name[:-1] if minor else name]
    base = (octave - 4) * 12 + root - 9
    return [base, base + (3 if minor else 4), base + 7, base + 12]


def env(n: int, attack: float, release: float) -> np.ndarray:
    t = np.arange(n) / SR
    e = np.minimum(1, t / max(attack, 1e-4))
    tail = int(release * SR)
    if tail and tail < n:
        e[-tail:] *= np.linspace(1, 0, tail)
    return e


def saw(f: float, n: int, detune: float = 0.0) -> np.ndarray:
    t = np.arange(n) / SR
    ph = (t * f * (1 + detune)) % 1
    return 2 * ph - 1


def pad_bar(notes: list[float], n: int) -> np.ndarray:
    out = np.zeros(n)
    for s in notes:
        f = freq(s)
        out += saw(f, n, 0.003) + saw(f, n, -0.004)
    out = np.convolve(out, np.ones(24) / 24, mode="same")  # soft top end
    return out * env(n, 0.35, 0.25) * 0.05


def kick(n: int) -> np.ndarray:
    t = np.arange(n) / SR
    f = 45 + 110 * np.exp(-t * 28)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 7.5) * 0.9


def noise_hit(n: int, decay: float, smooth: int) -> np.ndarray:
    x = rng.standard_normal(n)
    if smooth > 1:
        x = x - np.convolve(x, np.ones(smooth) / smooth, mode="same")  # high-pass
    return x * np.exp(-np.arange(n) / SR * decay)


def pluck(f: float, n: int) -> np.ndarray:
    t = np.arange(n) / SR
    tri = 2 * np.abs(2 * ((t * f) % 1) - 1) - 1
    return tri * np.exp(-t * 9) * 0.16


def add(buf: np.ndarray, x: np.ndarray, at: int, gain: float = 1.0) -> None:
    if at >= len(buf):
        return
    end = min(len(buf), at + len(x))
    buf[at:end] += x[: end - at] * gain


def build(plan: dict) -> np.ndarray:
    bpm = plan["bpm"]
    beat = 60 / bpm
    bar = beat * 4
    total_bars = sum(s["bars"] for s in plan["sections"])
    n = int((total_bars * bar + (3.0 if plan.get("end_ring", True) else 0)) * SR)
    pad = np.zeros(n)
    drums = np.zeros(n)
    bass = np.zeros(n)
    arp = np.zeros(n)
    chords = plan["chords"]
    b = 0
    for si, sec in enumerate(plan["sections"]):
        kind = sec["kind"]
        nxt = plan["sections"][si + 1]["kind"] if si + 1 < len(plan["sections"]) else None
        for k in range(sec["bars"]):
            ch = chords[b % len(chords)]
            t0 = int(b * bar * SR)
            nbar = int(bar * SR)
            last = kind == "outro" and k == sec["bars"] - 1
            add(pad, pad_bar(chord_notes(ch), nbar + (int(2.5 * SR) if last else int(0.3 * SR))), t0)
            root = chord_notes(ch, 2)[0]
            if kind in ("build", "drop"):
                for e in range(8):
                    nn = int(beat / 2 * SR * 0.9)
                    tone = np.sin(2 * np.pi * freq(root) * np.arange(nn) / SR) * env(nn, 0.005, 0.05)
                    add(bass, np.tanh(tone * 1.6) * (0.32 if kind == "drop" else 0.22), t0 + int(e * beat / 2 * SR))
                for e in range(8):
                    if e % 2 == 1 or kind == "drop":
                        add(drums, noise_hit(int(0.08 * SR), 60, 6), t0 + int(e * beat / 2 * SR), 0.05 if e % 2 else 0.025)
            if kind == "drop":
                for q in range(4):
                    add(drums, kick(int(0.45 * SR)), t0 + int(q * beat * SR), 0.85)
                for q in (1, 3):
                    add(drums, noise_hit(int(0.25 * SR), 18, 3), t0 + int(q * beat * SR), 0.16)
            if kind == "build" and k >= sec["bars"] - 1 and nxt in ("drop", "outro"):
                nn = nbar
                sw = rng.standard_normal(nn) * np.linspace(0, 1, nn) ** 2
                sw = sw - np.convolve(sw, np.ones(8) / 8, mode="same")
                add(drums, sw, t0, 0.07)
            if kind in ("drop", "break"):
                tones = chord_notes(ch, 5)
                for e in range(16):
                    add(arp, pluck(freq(tones[[0, 2, 1, 3][e % 4]]), int(beat / 4 * SR * 1.6)), t0 + int(e * beat / 4 * SR))
            if kind in ("drop",) and k == 0:
                add(drums, noise_hit(int(1.2 * SR), 3.5, 2), t0, 0.08)  # crash
            b += 1
    for stop in plan.get("stops", []):
        a, z = max(0, int((stop - beat) * SR)), min(n, int(stop * SR))
        if z > a:
            for layer in (drums, bass, arp):
                layer[a:z] *= np.linspace(1, 0, z - a) ** 6
    mix_l = pad * 1.0 + drums + bass + arp * 0.9
    mix_r = pad * 0.95 + drums + bass * 0.98 + np.roll(arp, int(0.012 * SR)) * 0.9  # a little width
    out = np.stack([mix_l, mix_r], axis=1)
    out /= max(1e-9, np.abs(out).max()) / 0.7
    fade = int(0.04 * SR)
    out[:fade] *= np.linspace(0, 1, fade)[:, None]
    out[-int(1.5 * SR):] *= np.linspace(1, 0, int(1.5 * SR))[:, None]
    return out


KINDS = ("intro", "build", "drop", "break", "outro")


def problems(plan) -> list:
    """Every problem with a plan, all at once."""
    if not isinstance(plan, dict):
        return ["the plan must be a JSON object"]
    out = []
    bpm = plan.get("bpm")
    if not (isinstance(bpm, (int, float)) and not isinstance(bpm, bool) and 40 <= bpm <= 200):
        out.append(f"bpm must be a number from 40 to 200, got {bpm!r}")
    chords = plan.get("chords")
    if not (isinstance(chords, list) and chords and all(isinstance(c, str) and (c[:-1] if c.endswith("m") else c) in NOTES for c in chords)):
        out.append(f"chords must list chord names like Am, F, C, G, got {chords!r}")
    sections = plan.get("sections")
    if not (isinstance(sections, list) and sections):
        out.append("sections must list the bed's sections")
    else:
        for k, sec in enumerate(sections):
            if not (isinstance(sec, dict) and isinstance(sec.get("bars"), int) and sec["bars"] >= 1 and sec.get("kind") in KINDS):
                out.append(f"sections[{k}] must be {{bars: 1 or more, kind: {' | '.join(KINDS)}}}, got {sec!r}")
    stops = plan.get("stops", [])
    if not (isinstance(stops, list) and all(isinstance(t, (int, float)) and not isinstance(t, bool) and t > 0 for t in stops)):
        out.append(f"stops must list seconds, got {stops!r}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("plan")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    try:
        with open(a.plan, encoding="utf-8") as f:
            plan = json.load(f)
    except (OSError, ValueError) as e:
        print(f"plan: cannot read {a.plan} ({e})", file=sys.stderr)
        raise SystemExit(2)
    bad = problems(plan)
    if bad:
        print("\n".join(bad), file=sys.stderr)
        raise SystemExit(2)
    out = build(plan)
    try:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        with wave.open(a.out, "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes((out * 32767).astype("<i2").tobytes())
    except OSError as e:
        print(f"cannot write {a.out}: {e}", file=sys.stderr)
        raise SystemExit(1)
    print(f"{a.out}: {len(out) / SR:.2f} s at {plan['bpm']} bpm")


if __name__ == "__main__":
    main()
