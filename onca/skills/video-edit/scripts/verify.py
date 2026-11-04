#!/usr/bin/env python3
"""Self-check a rendered short before the founder sees it.

usage: verify.py FINAL.mp4 --edl EDIT_DIR/edl.json --dir VERIFY_DIR [--fix WRONG=RIGHT ...] [--lufs -16]

1. Re-transcribes the output and diffs it against the approved words (edl.json words_out).
2. Checks the words on both sides of every cut are heard near the cut (nothing clipped).
3. Measures loudness (integrated LUFS, true peak) and the duration against the EDL.
4. Writes a 14-frame contact sheet: open it and look before reporting.
Writes VERIFY_DIR/verify.md and verify.json; exit code 0 even on warnings (Claude judges).
"""
import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import core, shell  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("final")
    ap.add_argument("--edl", required=True)
    ap.add_argument("--dir", required=True)
    ap.add_argument("--fix", action="append", default=[])
    ap.add_argument("--lufs", type=float, default=-16.0)
    a = ap.parse_args()
    d = Path(a.dir)
    d.mkdir(parents=True, exist_ok=True)
    edl = json.loads(Path(a.edl).read_text())
    info = shell.probe(a.final)
    shell.extract_wav(a.final, d / "final16k.wav")
    heard = core.apply_fixes(core.words_from_parakeet(shell.parakeet_json(d / "final16k.wav", d)), core.parse_fixes(a.fix))
    expected = [w["text"] for w in edl["words_out"]]
    diff = core.word_diff(expected, [w["text"] for w in heard])
    acc = core.word_accuracy(expected, [w["text"] for w in heard])
    clipped = core.clipped_at_cuts(core.boundary_words(edl["words_out"], edl["ranges"]), heard)
    loud = core.parse_ebur128(shell.ffmpeg_log(["-i", a.final, "-vn", "-af", "ebur128=peak=true"]))
    sheet = d / "contact-final.png"
    shell.contact_sheet(a.final, core.sheet_times(info["duration"], 14), sheet)
    checks = {
        "words": "ok" if acc >= 0.95 else "warn",
        "cuts": "ok" if not clipped else "warn",
        "loudness": "ok" if loud["I"] is not None and abs(loud["I"] - a.lufs) <= 1.0 and (loud["TP"] or 0) <= -1.0 else "warn",
        "duration": "ok" if abs(info["duration"] - edl["total"]) <= 0.15 else "warn",
    }
    res = {"checks": checks, "accuracy": acc, "diff": diff, "clipped": clipped, "loudness": loud,
           "duration": info["duration"], "edl_total": edl["total"], "size": f"{info['width']}x{info['height']}", "sheet": str(sheet),
           "heard": " ".join(w["text"] for w in heard)}
    (d / "verify.json").write_text(json.dumps(res, indent=1))
    md = [f"# Self-check: {Path(a.final).name}", "",
          f"- words: {checks['words']} ({acc:.0%} of the approved words heard, {len(diff)} differences)",
          f"- cuts: {checks['cuts']} ({len(edl['ranges']) - 1} cuts, {len(clipped)} with a word not heard next to it)",
          f"- loudness: {checks['loudness']} ({loud['I']} LUFS integrated, true peak {loud['TP']} dBFS, target {a.lufs})",
          f"- duration: {checks['duration']} ({info['duration']:.2f} s, EDL {edl['total']:.2f} s, {info['width']}x{info['height']})",
          f"- frames: {sheet} (look at it)", "", "## Differences (expected -> heard)", ""]
    md += [f"- {x['op']}: \"{x['expected']}\" -> \"{x['got']}\"" for x in diff] or ["- none"]
    md += ["", "## Cuts with a word not heard nearby", ""]
    md += [f"- cut {c['cut']} at {c['at']:.2f} s: {', '.join(c['missing'])}" for c in clipped] or ["- none"]
    md += ["", "## Heard", "", res["heard"]]
    (d / "verify.md").write_text("\n".join(md) + "\n")
    shell.log(" | ".join(f"{k} {v}" for k, v in checks.items()) + f" -> {d / 'verify.md'}")


if __name__ == "__main__":
    main()
