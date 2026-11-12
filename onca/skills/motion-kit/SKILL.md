---
name: motion-kit
description: Onca production kit. Tested motion parts for short videos (word-by-word headlines, highlight boxes, captions on the voice, rolling counters, a tilted card grid, pop-ins, slapped-on labels, whips, charts drawing in, focus pulls, spotlight stages, chat bubbles, one shape morphing into the next), a licensed pack of props, paper, fonts and sound effects, and tools that place the effects on the motion, snap cues to the music's beats, record the music bed's licence and cut product photos out, free and local. Use when a video should look like a pro reel, when the founder shares a reference video to copy, or when a composition needs motion, props, sound effects or a music bed.
---

# Motion kit (Onca production kit)

One file per video, `cues.json`, says which part moves which element when. One runtime, `motion.js`, turns that file into every frame, so any frame renders on its own, and the same file tells the sound tool where the effects go. Every bundled file is free for commercial posts and ads (CC0, OFL or made by Onca), listed in `assets/LICENSES.json`.

Paths below are relative to this skill's folder. `PY` is the Python command: `python3` on a Mac, `py -3 -X utf8` on Windows (the `video-render` skill's `## Windows` has the installs; every step here runs the same on both, and `kit.py pick` serves its page from this computer and opens the default browser). Run `scripts/kit.py` by its absolute path with `PY`. Exit 0 is done, 2 is bad input (every problem listed at once), 1 is a tool that failed (named, with its last lines).

## The work loop

1. **Start a project** (a folder of its own, never inside this plugin): `PY scripts/kit.py new PROJECT [--size 1080x1920] [--fps 30] [--duration 12]`. It writes `index.html`, `cues.json`, `brand.json` and `kit/` (the runtime, styles, props, paper, fonts).
2. **Brand**: read `get_brand_kit`, save the answer as `kit.json`, then `PY scripts/kit.py brand PROJECT --kit kit.json [--fonts DIR]`. It fills only the tokens `brand.json` leaves unset, each colour by its role's test (paper light, ink readable on it, accent colourful and readable), and copies each brand font's file into `PROJECT/fonts/` from `--fonts` folders (the product's repo) or the system's fonts; a font it cannot find is named with its download link: fetch it into `PROJECT/fonts/` and run `brand` again. Set the accent yourself when the brand's signature colour is not the one picked.
3. **Copy a reference** when the founder shares one: write its recipe first (`references/recipe.md`), then `PY scripts/kit.py recipe cues RECIPE.json --out PROJECT/cues.json` for a first `cues.json`.
4. **Write the page and the cues**: the elements go in `index.html` inside `#main`, each with the `id` its cue names; positions, sizes and type are yours, motion is the kit's. Pick parts from `references/parts.md`, props and paper from `references/props.md`.
5. **Voice and music**: **Ask which voice, every video, before any voiceover.** Price the script first with `make_voiceover(lines, dry_run: true)` (free), then ask in plain words: "Onca voice sounds much more natural (costs N credits), or the free voice on your computer?" Then open the matching picker, where the founder plays each voice and clicks one; never list voices in chat. Onca voice: `sample_voices` (free) with a line of the script, open its `listen_at` page (the Brand kit's Narrator voice card: a grid of voice names, each with a small play button; a click on a name picks it) in the founder's browser, and read the pick back from `get_brand_kit` (`narrator`). The free voice: make a short sample of each local voice, list them in a `choices.json`, and run the `motion-kit` skill's `kit.py pick choices.json --out pick.json`, which opens the same kind of page on the founder's computer (only the names, a play button each, one click picks) and returns the pick. Make one WAV per line (the `voice` skill), then `PY scripts/kit.py voice PROJECT --lines lines.json [--asr asr.json] [--tempo 1.05]` tightens each line (its silent ends trimmed, every pause inside cut to `--max-pause` 0.28 s; `--keep-pauses` keeps them, `--raw` uses the files as they are; `--tempo` 0.9 to 1.15 speeds the voice gently, pitch kept), places the lines (`{"lead": 0.3, "gap": 0.25, "lines": [{"id", "file", "text", "at"?}]}`) into `voice.wav` and writes `words.json` with the script's own spelling (times spread over each line; for word-exact times, transcribe the `voice.wav` it wrote with `video-edit`'s `transcribe.py` and run `voice` again with `--asr` that file); name it in `cues.json` as `"words": "words.json"`. Key the motion to the words: a cue's `at` can be `{"line": "hook", "word": 3, "offset": -0.1}` (word 1 is the line's first), so a pop lands as its word is said and moves with the voice when a line is remade. Line ids are letters, digits, `_` and `-`. If the voice runs past the video, `voice` says the length to set in `cues.json`, and `sync` stops until it fits, then sets the page's. A music bed only through Higgsfield and only with the founder's yes for that run (`references/sound.md`); then `PY scripts/kit.py beats PROJECT --music BED` so cues marked `snap` land on the beat.
6. **Sync**: `PY scripts/kit.py sync PROJECT` after every change to `cues.json`, `brand.json`, the page or the words. It checks every cue against the page and writes `cues.js`, `brand.css` and the root's length. `cues.json` is never rewritten.
7. **Check and render**: `PY scripts/kit.py check PROJECT` runs the engine's check and sets apart the "no sound" findings the kit expects (the sound is mixed in step 8); fix every error. Then render with the `video-render` skill's engine route (a draft first) and look at the frames.
8. **Sound**: `PY scripts/kit.py sound PROJECT --video RENDER.mp4 [--voice VOICE.wav] [--music BED]`. It places the effects on the motion, mixes voice, music and effects through `video-edit`'s timeline render at -16 LUFS and writes `PROJECT/out/with-sound.mp4`.
9. **Review** to `video-render`'s checklist before the video goes to the library, a post or the founder.

## Rules that make it look pro

- One idea per beat and one moving thing at a time; the eye follows the newest motion. Give each headline its read time.
- Motion has a reason: a part enters when the voice says it, leaves when the next idea starts. Never decorate.
- Ease out on entries (things arrive fast and settle), springs for anything physical (pops, labels, bubbles), linear only for counters' steady roll and continuous drifts.
- Sound only where something happens on screen; no effect under every word. The kit already skips an effect within 0.12 s of the one before.
- The brand kit's fonts and colours. With no brand font, set `display_font` and `body_font` in `brand.json` to a bundled font (DM Serif Display for display, Caveat for handwriting) or to a font file added under `font_files`, so every machine renders the same type; never leave it to a system default font.
- Product UI is never a 1x screenshot (its text comes out tiny and soft): rebuild the card or screen in HTML from the app's theme (or open the product's own page) and shoot it at 3x with `PY scripts/kit.py shot card.html card.png --scale 3`, then show it at a third of its pixels inside a `.om-cutout` frame (`references/props.md`).
- Product photos cut out cleanly (`PY scripts/kit.py cutout IN.jpg OUT.png --trim`): Apple Vision on macOS 14+, else rembg with the open `isnet-general-use` model (the tool prints the command; nothing installs itself, so ask the founder before installing a missing tool). Product UI stays flat and sharp.

## Files

- `references/parts.md`: the 13 parts, each with its use, timing, easing, layering, do and don't.
- `references/props.md`: props, paper textures, torn labels, sticky notes, polaroids, fonts.
- `references/sound.md`: effects, beats, the Higgsfield music flow and the founder's legal position.
- `references/recipe.md`: make it like this video.
- `assets/LICENSES.json`: source, author, licence link and date for every bundled file.

## Other skills

- How to write and animate a composition: `hyperframes` (its `references/motion.md`, `sound.md`, `captions.md`). The render route and contract: `video-render`. Narration: `voice`. Captions on real footage, cuts and the music mix: `video-edit`. Product footage: `screen-demo`. Cutaways: `b-roll`. Short launch videos from templates: `launch-video`.
