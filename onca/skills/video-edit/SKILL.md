---
name: video-edit
description: Edit a raw talking video (a screen recording with voice, or a person on camera) into a tight captioned short, free and fully local. Word-level transcript, a cut list the founder approves before anything renders, filler and false-start removal, pause tightening, loudness, 9:16 and 16:9 reframes, big word-timed captions, and a self-check of the output. Use when the user says edit this video, cut this recording, trim the ums, remove the pauses, make a short from this, add captions or subtitles, or turn this into a reel, TikTok or Short.
---

# Video edit

Turn one raw talking video into a short (30 s or less unless asked otherwise) in 9:16 and 16:9 with burned-in captions. Everything runs on the founder's Mac for free: ffmpeg, parakeet-mlx, PySceneDetect, HyperFrames. Never call a paid service (Higgsfield, HeyGen, ElevenLabs, OpenAI or any other pay-per-use API) from this skill; if a step seems to need one, find the free route or tell the user what cannot be done free.

The decisions are yours (what to keep, which take, where captions go); the scripts only measure, build and render. The founder approves the cut list before any render.

## Setup check

- Run `python3 ../video-render/scripts/doctor.py check` from this skill's folder. It lists what is missing (`ffmpeg`, `ffprobe`, `parakeet-mlx` for word timestamps, `scenedetect`, Node 22+) with the install command for each; show the founder the commands and run them only after their yes. A Homebrew ffmpeg often has no `drawtext` and no `subtitles` filter, which is why captions go through the render engine.
- Captions render through the video-render skill's pinned engine (the video-render skill's `scripts/engine`); `captions.py` finds it by its absolute path and Node 22+ itself, so never create a wrapper or alias named `hf`.
- Scripts are stdlib Python: run them with `python3`. `S` is this skill's `scripts/` folder (the absolute path of the folder this SKILL.md is in, plus `/scripts`).
- Licences of the free models the founder's tools download: parakeet-mlx's default model, `mlx-community/parakeet-tdt-0.6b-v3` (from NVIDIA's `parakeet-tdt-0.6b-v3`), is CC-BY-4.0 (https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3): commercial use is allowed with attribution, and the transcript is a working file, never shipped in the video. Nothing here redistributes a model.

Work in an `edit/` folder next to the source (or the scratchpad); never write into the skill folder.

## The process

### 1. Transcribe

```bash
python3 $S/transcribe.py RAW.mp4 --out edit/words.json --fix "Akme=Acme"
```

- Fillers (um, uh) are kept on purpose: they are what the cut removes.
- Read the first output and add a `--fix WRONG=RIGHT` for every misheard name (the product, a person, a brand); use the same fixes in every later command.
- Word edges are pulled out of detected silence, because parakeet's times drift into pauses. Raise `--silence-db` toward `-30dB` for a noisy room.
- Transcription runs offline against the cached model (the hub check alone can take minutes); the first run ever downloads it.

### 2. Analyze

```bash
python3 $S/analyze.py RAW.mp4 --dir edit --words edit/words.json
```

Writes `edit/analysis.json` (probe, silences, loudness, frozen picture, shots), `edit/contact.png` (14 frames) and `edit/takes.md`: the transcript in phrases with word indices (`#12-#20`), pauses, `{fillers}` and runs said twice. Read `takes.md` and look at `contact.png`.

### 3. Plan the cut

Write `edit/plan.json` from `takes.md`:

```json
{
  "keep": [{"from": 0, "to": 5, "reason": "hook"}, {"from": 17, "to": 24, "reason": "the problem"}],
  "drop": [{"from": 6, "to": 16, "reason": "um + false start"}],
  "retext": {"82": "so"}
}
```

- `keep` spans are word indices, inclusive, in play order. Split a span around every word you drop inside it.
- Drop: hard fillers (um, uh, er), filler phrases where they carry nothing (like, you know, I mean, basically), false starts ("wait, let me say that again" and the half sentence before it), every repeated take but one (usually the last, unless an earlier one is cleaner), dead screen time (a frozen picture while nothing is said).
- Keep the sense: no cut that changes a claim, and check the result still reads as sentences.
- `drop` only labels the cut lines for the founder; `retext` changes caption wording per word index (a capital after a removed sentence end, "So" after a comma).
- Over the target length: cut whole sentences by importance, never speed the voice up.

```bash
python3 $S/edl.py RAW.mp4 --words edit/words.json --plan edit/plan.json --dir edit
```

Writes `edit/edl.json` and `edit/edl.md`. Pauses inside a kept span over 0.4 s become 0.15 s (`--max-pause`, `--tight-pause`); edges get 60 ms before and 90 ms after the words, never reaching into a dropped word, and snap to frames.

### 4. STOP: the founder approves `edl.md`

Show the founder `edl.md` (before and after length, what stays, every cut in one line, the pieces). Do not render until they say OK. Apply their changes to `plan.json`, rebuild, show again.

### 5. Render

```bash
python3 $S/render.py edit/edl.json --dir edit --sizes 1080x1920:9x16,1920x1080:16x9
```

One master cut (every audio piece fades 25 ms in and out, so cuts never click; pieces butt-join so caption times stay exact), loudness to -16 LUFS in two passes, H.264 yuv420p +faststart, AAC 48 kHz. Reframe: same aspect scales; a narrower target (16:9 to 9:16) crops around `--focus-x` (0 left, 1 right: put the speaker's face or the active UI in the frame; look at the contact sheet); a wider target (9:16 to 16:9) fits the picture over a blurred copy of itself (`--mode fit` forces this for a narrower target too).

### 6. Captions

```bash
python3 $S/captions.py edit/edl.json --video edit/cut-9x16.mp4 --out edit/final-9x16.mp4 [--band-top 1300 --band-height 140]
python3 $S/captions.py edit/edl.json --video edit/cut-16x9.mp4 --out edit/final-16x9.mp4
```

- One phrase at a time (up to 4 words, broken at punctuation and pauses, no lone trailing word), the spoken word lit in the accent colour, Montserrat Black 58-92 px with a stroke and a dark box behind the words.
- Portrait captions stay inside TikTok's safe zone (x 120-940, y 220-1440) and, for Instagram, inside the middle 4:5 its home feed shows (y 285-1635; not verified: Instagram publishes no numbers for it, size guides report it), so y 285-1440. Pick the band from the contact sheet: below the speaker's face, off text already in the picture. The script warns when the band runs below y 1440 or starts above y 285.
- It writes a HyperFrames project (`<out>-hf/`), runs `check` (its `check.json`; the `film_silent` warning is expected: the video renders muted and its sound is copied back afterwards so loudness stays as measured), renders, and muxes the audio.
- To restyle, edit `compose.py` or the `-hf` project with this plugin's `hyperframes` skill.

### 7. Self-check, before the founder sees anything

```bash
python3 $S/verify.py edit/final-9x16.mp4 --edl edit/edl.json --dir edit/verify-9x16 --fix "Akme=Acme"
```

Checks: the re-transcript against the approved words (95% or more; a single swapped short word is usually recognizer noise, a missing phrase is a real cut error), the word on each side of every cut heard near it (nothing clipped), loudness within 1 LU of -16 with true peak at or under -1 dBFS, duration against the EDL. Then open `contact-final.png` yourself and look for captions over faces or on-screen text, a caption cut off, a black or frozen frame, a bad crop. Fix, re-render, check again (at most 3 rounds, then tell the founder what is left).

### 8. Founder review

Give the founder the two finals, the before and after length, what the self-check found, and anything you could not fix. Listening is theirs: you cannot hear the audio, so say so and give the numbers.

## Files

- `scripts/core.py`: every decision as a pure function (parsers, word refinement, the cut, re-timing, caption groups, diffs, reframe filters).
- `scripts/compose.py`: the HyperFrames HTML (pure).
- `scripts/shell.py`: the subprocess calls (ffmpeg, ffprobe, parakeet, scenedetect).
- `transcribe.py`, `analyze.py`, `edl.py`, `render.py`, `captions.py`, `verify.py`: one job each.

## Limits

- One source file per edit; for several takes, edit each, then join the finals, or extend `build_ranges` with a source per range.
- Captions are English-first (word timing comes from parakeet's sub-word tokens).
- Music beds, B-roll, zooms and title cards are not built in; add them in the `-hf` project with this plugin's `hyperframes` skill (bundled or synthesized sound with a licence you can name, never paid generation without the founder's yes).
