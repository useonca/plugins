"""Pure decisions for the video-edit skill: no files, no subprocesses.

Every function takes and returns plain values so the cut logic is tested with
lists of dicts. The shell scripts next to this file do the ffmpeg / parakeet
work and call into here.

Ideas borrowed from browser-use/video-use (MIT, github.com/browser-use/video-use):
word-boundary cuts with 30-200 ms padding, short fades at every segment edge,
and output-timeline offsets for captions (output = word - range start + range offset).
"""

from __future__ import annotations

import difflib
import math
import re

FILLERS = {"um", "uh", "erm", "er", "ah", "hmm", "mm", "like", "you know", "i mean", "so", "basically", "actually"}
HARD_FILLERS = {"um", "uh", "erm", "er", "ah", "hmm", "mm"}  # always a filler; the rest depend on context

# ---------------------------------------------------------------- text helpers


def norm(text: str) -> str:
    """Lowercase, strip punctuation; keeps apostrophes inside words."""
    t = text.lower().replace("\u2019", "'")
    t = re.sub(r"[^a-z0-9' ]+", " ", t)
    return " ".join(w.strip("'") for w in t.split() if w.strip("'"))


def is_hard_filler(text: str) -> bool:
    return norm(text) in HARD_FILLERS


# ---------------------------------------------------------------- parakeet -> words


def words_from_parakeet(doc: dict) -> list[dict]:
    """Turn parakeet-mlx JSON (sentences -> sub-word tokens) into words.

    A token whose text starts with a space begins a new word. Returns
    [{"i", "text", "start", "end"}] with times in seconds, rounded to ms.
    """
    words: list[dict] = []
    for sentence in doc.get("sentences", []):
        space_before = True
        for tok in sentence.get("tokens", []):
            text = tok.get("text", "")
            if not text:
                continue
            starts_word = text[0].isspace() or space_before or not words
            piece = text.strip()
            space_before = not piece  # a lone space token ("for", " ", "3", "0") opens the next word
            if not piece:
                continue
            punct = not re.search(r"\w", piece)
            if words and punct:
                words[-1]["text"] += piece  # punctuation never stretches a word's end into the pause
            elif starts_word or words[-1].get("_closed"):
                words.append({"text": piece, "start": tok["start"], "end": tok["end"]})
            else:
                words[-1]["text"] += piece
                words[-1]["end"] = tok["end"]
        if words:
            words[-1]["_closed"] = True  # a sentence end always closes the word
    out = []
    for i, w in enumerate(words):
        out.append({"i": i, "text": w["text"], "start": round(w["start"], 3), "end": round(w["end"], 3)})
    return out


def speech_regions(silences: list[dict], duration: float) -> list[tuple[float, float]]:
    """The complement of the silences inside [0, duration]."""
    out, t = [], 0.0
    for sil in sorted(silences, key=lambda x: x["start"]):
        if sil["start"] > t:
            out.append((t, sil["start"]))
        t = max(t, sil["end"])
    if t < duration:
        out.append((t, duration))
    return out


def refine_with_silences(words: list[dict], silences: list[dict], min_word: float = 0.1) -> list[dict]:
    """Snap word edges to the speech the audio actually holds.

    parakeet times sit on an 80 ms grid and drift: a sentence's last word can
    land inside the pause after it, a word after a pause can start early. Each
    word goes to the speech region holding its midpoint. A word whose midpoint is
    in a silence goes back when it ends a phrase (punctuation), forward when the
    word before it did, else to the region whose edge is nearest its start. Inside
    its region a word is clamped, and a word squeezed under min_word is given
    the region's last (or first) min_word.
    """
    if not words:
        return []
    duration = max(max(w["end"] for w in words), max((x["end"] for x in silences), default=0.0)) + 0.5
    regions = speech_regions(silences, duration)
    if not regions:
        return [dict(w) for w in words]

    def region_for(k_word, w):
        mid = (w["start"] + w["end"]) / 2
        for k, (rs, re_) in enumerate(regions):
            if rs <= mid <= re_:
                return k
        before = max((k for k, r in enumerate(regions) if r[1] <= mid), default=0)
        after = min((k for k, r in enumerate(regions) if r[0] >= mid), default=len(regions) - 1)
        ends_phrase = w["text"][-1:] in ".!?,;:"
        prev_ended = k_word > 0 and words[k_word - 1]["text"][-1:] in ".!?,;:"
        if ends_phrase and not prev_ended:
            return before  # "right there." spilled into the pause after it
        if prev_ended and not ends_phrase:
            return after  # "Uh, try": the word opens the next phrase
        return min((before, after), key=lambda k: min(abs(w["start"] - regions[k][0]), abs(w["start"] - regions[k][1])))

    out = []
    for k_word, w in enumerate(words):
        rs, re_ = regions[region_for(k_word, w)]
        s, e = min(max(w["start"], rs), re_), min(max(w["end"], rs), re_)
        if e - s < min_word:
            if s >= re_ - min_word:
                s, e = max(rs, re_ - min_word), re_
            else:
                e = min(re_, s + min_word)
        out.append(dict(w, start=round(s, 3), end=round(e, 3)))
    for a_, b_ in zip(out, out[1:]):  # keep words in order and non-overlapping
        if b_["start"] < a_["end"]:
            if a_["start"] < b_["start"]:
                a_["end"] = b_["start"]
            else:
                b_["start"] = a_["end"]
                b_["end"] = max(b_["end"], b_["start"])
    return out


def apply_fixes(words: list[dict], fixes: dict[str, str]) -> list[dict]:
    """Correct names the recognizer gets wrong ({"Akme": "Acme"}), keeping punctuation."""
    table = {norm(k): v for k, v in fixes.items()}
    out = []
    for w in words:
        key = norm(w["text"])
        if key in table:
            m = re.match(r"^(\W*)(.*?)(\W*)$", w["text"])
            w = dict(w, text=f"{m.group(1)}{table[key]}{m.group(3)}")
        out.append(w)
    return out


def parse_fixes(items: list[str]) -> dict[str, str]:
    """["Akme=Acme", ...] -> {"Akme": "Acme"}."""
    out = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"a fix is WRONG=RIGHT, got {item!r}")
        a, b = item.split("=", 1)
        out[a.strip()] = b.strip()
    return out


# ---------------------------------------------------------------- ffmpeg log parsers


def parse_silences(log: str, duration: float | None = None) -> list[dict]:
    """silencedetect stderr -> [{"start", "end", "dur"}]. An open silence ends at duration."""
    out, start = [], None
    for line in log.splitlines():
        m = re.search(r"silence_start: (-?[\d.]+)", line)
        if m:
            start = max(0.0, float(m.group(1)))
            continue
        m = re.search(r"silence_end: ([\d.]+) \| silence_duration: ([\d.]+)", line)
        if m and start is not None:
            out.append({"start": round(start, 3), "end": round(float(m.group(1)), 3), "dur": round(float(m.group(2)), 3)})
            start = None
    if start is not None and duration is not None:
        out.append({"start": round(start, 3), "end": round(duration, 3), "dur": round(duration - start, 3)})
    return out


def parse_ebur128(log: str) -> dict:
    """ebur128 summary -> {"I": LUFS, "LRA": LU, "TP": dBTP or None}."""
    tail = log[log.rfind("Summary:"):] if "Summary:" in log else log
    def grab(pattern):
        m = re.search(pattern, tail)
        return float(m.group(1)) if m else None
    return {"I": grab(r"I:\s+(-?[\d.]+) LUFS"), "LRA": grab(r"LRA:\s+(-?[\d.]+) LU"), "TP": grab(r"Peak:\s+(-?[\d.]+) dBFS")}


def parse_freezes(log: str) -> list[dict]:
    """freezedetect stderr -> [{"start", "end", "dur"}]."""
    out, start = [], None
    for line in log.splitlines():
        m = re.search(r"freeze_start: ([\d.]+)", line)
        if m:
            start = float(m.group(1))
        m = re.search(r"freeze_end: ([\d.]+)", line)
        if m and start is not None:
            end = float(m.group(1))
            out.append({"start": round(start, 3), "end": round(end, 3), "dur": round(end - start, 3)})
            start = None
    return out


# ---------------------------------------------------------------- packed transcript


def pack_lines(words: list[dict], silences: list[dict] | None = None, break_gap: float = 0.5) -> list[str]:
    """One line per phrase: `[start-end] #first-#last text`, gaps over break_gap shown.

    Hard fillers are wrapped in {braces} so they stand out. This is what Claude
    reads to plan the cut: word indices make the plan exact.
    """
    lines, phrase = [], []

    def flush():
        if phrase:
            text = " ".join("{" + w["text"] + "}" if is_hard_filler(w["text"]) else w["text"] for w in phrase)
            lines.append(f"[{phrase[0]['start']:07.2f}-{phrase[-1]['end']:07.2f}] #{phrase[0]['i']}-#{phrase[-1]['i']} {text}")

    for k, w in enumerate(words):
        if phrase and w["start"] - phrase[-1]["end"] >= break_gap:
            flush()
            lines.append(f"    ... pause {w['start'] - phrase[-1]['end']:.2f} s")
            phrase = []
        phrase.append(w)
    flush()
    return lines


def repeated_runs(words: list[dict], min_len: int = 4) -> list[dict]:
    """Find word runs said twice (a repeated take). Returns [{"first": (a, b), "again": (c, d)}].

    Only a hint for Claude: which take to keep is its call.
    """
    toks = [norm(w["text"]) for w in words]
    found, n = [], len(toks)
    i = 0
    while i < n:
        best = None
        for j in range(i + min_len, n):
            k = 0
            while j + k < n and i + k < j and toks[i + k] == toks[j + k] and toks[i + k]:
                k += 1
            if k >= min_len and (best is None or k > best[1]):
                best = (j, k)
        if best:
            j, k = best
            found.append({"first": (words[i]["i"], words[i + k - 1]["i"]), "again": (words[j]["i"], words[j + k - 1]["i"])})
            i += k
        else:
            i += 1
    return found


# ---------------------------------------------------------------- EDL


def snap(t: float, fps: float) -> float:
    """Round a time to the nearest frame so audio and video cut on the same instant."""
    return round(round(t * fps) / fps, 4)


def build_ranges(
    words: list[dict],
    keep: list[dict],
    *,
    fps: float = 30.0,
    duration: float | None = None,
    pad_before: float = 0.06,
    pad_after: float = 0.09,
    max_pause: float = 0.4,
    tight_pause: float = 0.15,
) -> list[dict]:
    """Keep spans (word index `from`..`to`, inclusive, with a `reason`) -> time ranges.

    - each span starts pad_before before its first word and ends pad_after after its
      last, never reaching into the neighbouring word (never clip a word);
    - a pause inside a span longer than max_pause is cut down to tight_pause
      (the range splits, half the kept pause on each side);
    - edges snap to the frame grid; ranges that touch are merged.
    """
    by_i = {w["i"]: w for w in words}
    order = [w["i"] for w in words]
    pos = {i: k for k, i in enumerate(order)}
    ranges: list[dict] = []
    for span in keep:
        a, b = span["from"], span["to"]
        if a not in by_i or b not in by_i or pos[a] > pos[b]:
            raise ValueError(f"bad keep span {span}")
        seg = [by_i[order[k]] for k in range(pos[a], pos[b] + 1)]
        prev_end = by_i[order[pos[a] - 1]]["end"] if pos[a] > 0 else 0.0
        next_start = by_i[order[pos[b] + 1]]["start"] if pos[b] + 1 < len(order) else (duration or seg[-1]["end"] + 1.0)
        start = max(seg[0]["start"] - pad_before, (prev_end + seg[0]["start"]) / 2, 0.0)
        cur = {"start": start, "reason": span.get("reason", ""), "words": [seg[0]["i"]]}
        for w0, w1 in zip(seg, seg[1:]):
            gap = w1["start"] - w0["end"]
            if gap > max_pause:
                half = tight_pause / 2
                cur["end"] = w0["end"] + max(half, min(pad_after, half))
                ranges.append(cur)
                cur = {
                    "start": w1["start"] - max(half, min(pad_before, half)),
                    "reason": f"{span.get('reason', '')} (pause {gap:.2f} s tightened to {tight_pause:.2f} s)".strip(),
                    "words": [],
                }
            cur["words"].append(w1["i"])
        cur["end"] = min(seg[-1]["end"] + pad_after, (seg[-1]["end"] + next_start) / 2 if next_start > seg[-1]["end"] else seg[-1]["end"] + pad_after)
        if duration is not None:
            cur["end"] = min(cur["end"], duration)
        ranges.append(cur)

    out: list[dict] = []
    for r in ranges:
        r = dict(r, start=snap(r["start"], fps), end=snap(r["end"], fps))
        if r["end"] <= r["start"]:
            r["end"] = round(r["start"] + 1 / fps, 4)
        if out and r["start"] <= out[-1]["end"] + 1e-6:
            out[-1]["end"] = max(out[-1]["end"], r["end"])
            out[-1]["words"] += r["words"]
            continue
        out.append(r)
    t = 0.0
    for r in out:
        r["out_start"] = round(t, 4)
        t += r["end"] - r["start"]
        r["out_end"] = round(t, 4)
    return out


def total(ranges: list[dict]) -> float:
    return round(sum(r["end"] - r["start"] for r in ranges), 3)


def cut_lines(words: list[dict], ranges: list[dict], drops: list[dict], duration: float) -> list[str]:
    """One line per removed stretch: time, length, the words in it and why."""
    kept = {i for r in ranges for i in r["words"]}

    def reason_for(ids):
        for d in drops:
            if any(d["from"] <= i <= d["to"] for i in ids):
                return d.get("reason", "")
        return "pause tightened" if not ids else "not in the keep list"

    lines, prev = [], 0.0
    bounds = [(r["start"], r["end"]) for r in ranges] + [(duration, duration)]
    for start, end in bounds:
        if start - prev > 0.01:
            ids = [w["i"] for w in words if w["i"] not in kept and w["start"] >= prev - 0.01 and w["end"] <= start + 0.01]
            text = " ".join(w["text"] for w in words if w["i"] in ids)
            label = f'"{text}"' if text else "(silence)"
            lines.append(f"- cut {prev:6.2f}-{start:6.2f} ({start - prev:4.2f} s) {label}: {reason_for(ids)}")
        prev = end
    return lines


def edl_markdown(words: list[dict], ranges: list[dict], drops: list[dict], duration: float, title: str = "Cut list") -> str:
    by_i = {w["i"]: w for w in words}
    kept_text = " ".join(by_i[i]["text"] for r in ranges for i in r["words"])
    after = total(ranges)
    out = [
        f"# {title}",
        "",
        f"**Length:** {duration:.1f} s before, {after:.1f} s after ({duration - after:.1f} s cut, {len(ranges)} pieces).",
        "",
        "## What stays",
        "",
        kept_text,
        "",
        "## Every cut",
        "",
        *cut_lines(words, ranges, drops, duration),
        "",
        "## Pieces kept",
        "",
    ]
    for k, r in enumerate(ranges):
        text = " ".join(by_i[i]["text"] for i in r["words"])
        out.append(f"{k + 1}. {r['start']:6.2f}-{r['end']:6.2f} -> {r['out_start']:5.2f}-{r['out_end']:5.2f} \"{text}\" ({r['reason']})")
    out += ["", "Reply OK to render, or say what to change."]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- re-timing and captions


def retime(words: list[dict], ranges: list[dict]) -> list[dict]:
    """Kept words on the output timeline: out = t - range.start + range.out_start."""
    by_i = {w["i"]: w for w in words}
    out = []
    for r in ranges:
        shift = r["out_start"] - r["start"]
        for i in r["words"]:
            w = by_i[i]
            s = max(w["start"], r["start"]) + shift
            e = min(w["end"], r["end"]) + shift
            out.append({"i": i, "text": w["text"], "start": round(s, 3), "end": round(e, 3)})
    return out


def tidy_text(words: list[dict], retext: dict | None = None) -> list[dict]:
    """Caption text after the cut: Claude's per-word rewrites (`retext`, keyed by word
    index), then a capital letter at the start and after every sentence end."""
    retext = {int(k): v for k, v in (retext or {}).items()}
    out, prev = [], None
    for w in words:
        text = retext.get(w["i"], w["text"])
        if text and (prev is None or prev[-1:] in ".!?"):
            text = text[0].upper() + text[1:]
        out.append(dict(w, text=text))
        prev = text
    return out


def caption_groups(words: list[dict], max_words: int = 4, max_chars: int = 24, gap: float = 0.45, lead: float = 0.05, tail: float = 0.12, min_start: float = 0.15) -> list[dict]:
    """Group words into on-screen phrases, one visible at a time.

    Phrases end at punctuation or a pause >= gap; a comma phrase joins the next
    one when both fit in one group (a one-word one always joins). A phrase too long for one group is split
    into even chunks, so no group is a lone trailing word. A group shows from
    just before its first word to just after its last, never overlapping the next.
    """
    def fits(ws):
        return len(ws) <= max_words and len(" ".join(w["text"] for w in ws)) <= max_chars

    phrases, cur = [], []
    for k, w in enumerate(words):
        cur.append(w)
        nxt = words[k + 1] if k + 1 < len(words) else None
        end = w["text"][-1:]
        if nxt is None or end in ".!?,;:" or nxt["start"] - w["end"] >= gap:
            phrases.append(cur)
            cur = []
    merged: list[list[dict]] = []
    for ph in phrases:  # a comma phrase joins the next when both fit, a one-word one always
        prev = merged[-1] if merged else None
        if prev and prev[-1]["text"][-1:] in ",;:" and ph[0]["start"] - prev[-1]["end"] < gap and (fits(prev + ph) or len(prev) == 1):
            merged[-1] = prev + ph
        else:
            merged.append(ph)
    groups = []
    for ph in merged:
        n = 1
        while True:
            q, r = divmod(len(ph), n)  # n chunks as even as possible, the longer ones first
            sizes = [q + 1] * r + [q] * (n - r)
            chunks, i = [], 0
            for sz in sizes:
                chunks.append(ph[i:i + sz])
                i += sz
            if all(fits(c) for c in chunks) or n >= len(ph):
                break
            n += 1
        groups += [{"words": c, "text": " ".join(w["text"] for w in c)} for c in chunks]
    for k, g in enumerate(groups):
        g["start"] = round(max(g["words"][0]["start"] - lead, min_start if k == 0 else 0.0), 3)
        g["end"] = round(g["words"][-1]["end"] + tail, 3)
    for a_, b_ in zip(groups, groups[1:]):
        if a_["end"] > b_["start"]:
            a_["end"] = b_["start"]
    return groups


# ---------------------------------------------------------------- self-check


def word_diff(expected: list[str], got: list[str]) -> list[dict]:
    """Compare approved words with a re-transcript (normalized). Returns the non-equal ops."""
    e = [norm(x) for x in expected if norm(x)]
    g = [norm(x) for x in got if norm(x)]
    ops = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=e, b=g, autojunk=False).get_opcodes():
        if tag != "equal":
            ops.append({"op": tag, "expected": " ".join(e[i1:i2]), "got": " ".join(g[j1:j2]), "at": i1})
    return ops


def word_accuracy(expected: list[str], got: list[str]) -> float:
    e = [norm(x) for x in expected if norm(x)]
    g = [norm(x) for x in got if norm(x)]
    if not e:
        return 1.0
    sm = difflib.SequenceMatcher(a=e, b=g, autojunk=False)
    return round(sum(b.size for b in sm.get_matching_blocks()) / len(e), 3)


def boundary_words(retimed: list[dict], ranges: list[dict]) -> list[dict]:
    """The last word before and first word after each cut, on the output timeline."""
    out = []
    for k in range(1, len(ranges)):
        t = ranges[k]["out_start"]
        before = [w for w in retimed if w["end"] <= t + 0.001]
        after = [w for w in retimed if w["start"] >= t - 0.001]
        out.append({"cut": k, "at": t, "before": before[-1]["text"] if before else None, "after": after[0]["text"] if after else None})
    return out


def clipped_at_cuts(boundaries: list[dict], heard: list[dict], window: float = 0.6) -> list[dict]:
    """A cut is suspect when a re-transcript lacks the word on either side of it near the cut."""
    bad = []
    for b in boundaries:
        near = {norm(w["text"]) for w in heard if abs(w["start"] - b["at"]) <= window or abs(w["end"] - b["at"]) <= window}
        missing = [x for x in (b["before"], b["after"]) if x and norm(x) not in near]
        if missing:
            bad.append({**b, "missing": missing})
    return bad


def sheet_times(duration: float, n: int = 14) -> list[float]:
    """n evenly spaced frame times inside (0, duration)."""
    step = duration / n
    return [round(step * (k + 0.5), 3) for k in range(n)]


def reframe_filter(src_w: int, src_h: int, dst_w: int, dst_h: int, focus_x: float = 0.5, mode: str = "auto") -> str:
    """ffmpeg filter for one output frame size.

    Same aspect: scale. Narrower target (16:9 -> 9:16): crop around focus_x (0..1),
    or `fit` letterboxes on a blurred copy. Wider target (9:16 -> 16:9): the
    picture fits the height over a blurred, darkened copy of itself.
    """
    src_ar, dst_ar = src_w / src_h, dst_w / dst_h
    if math.isclose(src_ar, dst_ar, rel_tol=0.01):
        return f"scale={dst_w}:{dst_h}:flags=lanczos,setsar=1"
    if mode == "auto":
        mode = "crop" if dst_ar < src_ar else "fit"
    if mode == "crop":
        if dst_ar < src_ar:
            cw = int(src_h * dst_ar) // 2 * 2
            x = int(max(0, min(src_w - cw, focus_x * src_w - cw / 2)))
            return f"crop={cw}:{src_h}:{x}:0,scale={dst_w}:{dst_h}:flags=lanczos,setsar=1"
        ch = int(src_w / dst_ar) // 2 * 2
        return f"crop={src_w}:{ch}:0:{(src_h - ch) // 2},scale={dst_w}:{dst_h}:flags=lanczos,setsar=1"
    return (
        f"split=2[bg][fg];"
        f"[bg]scale={dst_w}:{dst_h}:force_original_aspect_ratio=increase,crop={dst_w}:{dst_h},gblur=sigma=40,eq=brightness=-0.12:saturation=0.8[bgb];"
        f"[fg]scale={dst_w}:{dst_h}:force_original_aspect_ratio=decrease:flags=lanczos[fgs];"
        f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2,setsar=1"
    )


def cut_graph(ranges: list[dict], fade: float = 0.025, has_audio: bool = True) -> str:
    """filter_complex that trims every kept range and joins them.

    Each audio piece gets a short fade in and out, so a cut never clicks; the
    pieces butt-join, so the output timeline is exactly the sum of the ranges
    (the captions depend on that).
    """
    parts, labels = [], []
    for k, r in enumerate(ranges):
        d = round(r["end"] - r["start"], 4)
        parts.append(f"[0:v]trim=start={r['start']}:end={r['end']},setpts=PTS-STARTPTS[v{k}]")
        labels.append(f"[v{k}]")
        if has_audio:
            f = min(fade, d / 4)
            parts.append(f"[0:a]atrim=start={r['start']}:end={r['end']},asetpts=PTS-STARTPTS,"
                         f"afade=t=in:st=0:d={f},afade=t=out:st={round(d - f, 4)}:d={f}[a{k}]")
            labels.append(f"[a{k}]")
    n = len(ranges)
    parts.append("".join(labels) + f"concat=n={n}:v=1:a={1 if has_audio else 0}" + ("[v][a]" if has_audio else "[v]"))
    return ";".join(parts)


def parse_loudnorm(log: str) -> dict:
    """The JSON block loudnorm prints with print_format=json."""
    import json
    start = log.rfind("{")
    end = log.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no loudnorm JSON in the log")
    return json.loads(log[start:end + 1])


def loudnorm_apply(m: dict, target: float = -16.0, tp: float = -1.5, lra: float = 11.0) -> str:
    """Second loudnorm pass from the first pass's measurement (linear when possible)."""
    return (f"loudnorm=I={target}:TP={tp}:LRA={lra}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
            f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")


def parse_sizes(spec: str) -> list[tuple[int, int, str]]:
    """"1080x1920:9x16,1920x1080:16x9" -> [(1080, 1920, "9x16"), (1920, 1080, "16x9")]."""
    out = []
    for item in spec.split(","):
        size, _, name = item.partition(":")
        w, h = (int(x) for x in size.lower().split("x"))
        out.append((w, h, name or f"{w}x{h}"))
    return out
