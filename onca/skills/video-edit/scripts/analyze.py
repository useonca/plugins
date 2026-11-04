#!/usr/bin/env python3
"""Everything Claude reads before planning a cut, in one folder.

usage: analyze.py IN --dir EDIT_DIR [--words words.json]

Writes EDIT_DIR/analysis.json (probe, silences, loudness, freezes, shots),
EDIT_DIR/contact.png (14 frames) and, with --words, EDIT_DIR/takes.md: the
packed transcript with word indices, pauses and likely repeated takes.
"""
import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import core, shell  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--dir", required=True)
    ap.add_argument("--words")
    ap.add_argument("--silence-db", default="-35dB")
    ap.add_argument("--silence-min", type=float, default=0.3)
    a = ap.parse_args()
    d = Path(a.dir)
    d.mkdir(parents=True, exist_ok=True)
    info = shell.probe(a.src)
    res = {"probe": info}
    if info["has_audio"]:
        log = shell.ffmpeg_log(["-i", a.src, "-vn", "-af", f"silencedetect=noise={a.silence_db}:d={a.silence_min}"])
        res["silences"] = core.parse_silences(log, info["duration"])
        res["loudness"] = core.parse_ebur128(shell.ffmpeg_log(["-i", a.src, "-vn", "-af", "ebur128=peak=true"]))
    res["freezes"] = core.parse_freezes(shell.ffmpeg_log(["-i", a.src, "-an", "-vf", "freezedetect=n=-60dB:d=1"]))
    res["shots"] = shell.scenes(a.src, d)
    shell.contact_sheet(a.src, core.sheet_times(info["duration"], 14), d / "contact.png")
    (d / "analysis.json").write_text(json.dumps(res, indent=1))
    if a.words:
        words = json.loads(Path(a.words).read_text())
        lines = [f"# Takes: {Path(a.src).name} ({info['duration']:.1f} s)", "", "Word indices (#n) go into plan.json. {braces} = hard filler.", ""]
        lines += core.pack_lines(words, res.get("silences"))
        reps = core.repeated_runs(words)
        if reps:
            lines += ["", "## Said twice (pick one take)", ""]
            lines += [f"- #{r['first'][0]}-#{r['first'][1]} again at #{r['again'][0]}-#{r['again'][1]}" for r in reps]
        (d / "takes.md").write_text("\n".join(lines) + "\n")
    loud = res.get("loudness", {})
    shell.log(f"{info['duration']} s {info['width']}x{info['height']} @{info['fps']} | silences {len(res.get('silences', []))} | "
              f"I {loud.get('I')} LUFS | freezes {len(res['freezes'])} | shots {len(res['shots'])} -> {d}")


if __name__ == "__main__":
    main()
