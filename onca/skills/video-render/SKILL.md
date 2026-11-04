---
name: video-render
description: Onca's render contract and route for turning an HTML composition into a finished 9:16 (or 16:9) MP4 on the founder's Mac, free. Use it for every render the launch-video and video-edit skills ask for, and before the first video to check the Mac. It runs the pinned HyperFrames engine through its scripts/engine; read the hyperframes skill for how to write the composition.
---

# Video render

Everything renders locally and costs nothing. The engine is HyperFrames (HTML rendered to video, Apache 2.0), pinned to the version in `ENGINE.json`; its own two skills ship in this plugin as `hyperframes` (how to write and animate a composition) and `hyperframes-cli` (the commands). Paths below are from this skill's folder (the folder this SKILL.md is in): run each as that folder's absolute path plus the path, because commands run from the video's own folder.

## The engine route

- `ENGINE` below is the absolute path of this skill's `scripts/engine` (this skill's folder plus `/scripts/engine`). Run it from inside the video's project folder, which is where the engine looks for `index.html`: `cd <project> && sh "$ENGINE" <command> [args]`. Wherever the `hyperframes` or `hyperframes-cli` skill says `npx hyperframes <command>`, use `sh "$ENGINE" <command>` instead: it runs exactly the pinned version and puts a Node 22+ first on PATH.
- Never run the engine's `cloud` commands, `lambda`, `cloudrun`, `publish`, `render --cloud` or anything else that uploads, spends or needs an account. A render here is always local. Skip the engine's `usage` step (it reports a cloud plan, which a local render does not use).
- Before the first video of a session: `python3 scripts/doctor.py check`. Each missing item prints its install command (`brew install node@22`, `brew install ffmpeg`, `brew install uv`, `uv tool install parakeet-mlx`, `uv tool install scenedetect`, `uv tool install mlx-audio`). Show the founder what is missing and the commands, and run them only after their yes. `mlx_audio.tts.generate` is only needed for narration (the `voice` skill).
- Before every render: `sh "$ENGINE" check --json` in the project folder; fix every error and weigh every warning.

## The render contract

Every video Onca's method makes meets this unless the founder asks otherwise:

- 1080 x 1920 (9:16), 30 fps, H.264 `yuv420p` with `+faststart`, AAC 48 kHz, loudness about -16 LUFS integrated with true peak at or under -1 dBFS. A 16:9 cut is 1920 x 1080.
- Words and key UI inside the safe box x 120 to 940, y 220 to 1440 (portrait); for Instagram also inside y 285 to 1635, the middle 4:5 its home feed shows (not verified: Instagram publishes no numbers for it, size guides report it; check a real post before a paid ad). UI text 34 px or more on screen.
- One change at a time: only one text element changes at any moment, and every headline gets its read time.
- A first frame that works as the thumbnail, the logo at the end, no copyrighted music.

## Render and finish

1. Render, in the project folder: `sh "$ENGINE" render --quality delivery --output <name>-raw.mp4` (`--quality draft` for a quick look).
2. Finish to the contract (H.264, yuv420p, faststart, loudness). With sound:
   ```bash
   ffmpeg -y -i <name>-raw.mp4 -c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p -r 30 \
     -af loudnorm=I=-16:TP=-1:LRA=11 -c:a aac -ar 48000 -b:a 192k -movflags +faststart <name>.mp4
   ```
   A silent video: drop the `-af ... -b:a 192k` part and add `-an`.
3. Check it: `ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,width,height,pix_fmt,r_frame_rate -of json <name>.mp4` must say `h264`, the size, `yuv420p` and `30/1`.
4. Look at it: a contact sheet of 14 evenly spaced frames (`D` is the length in seconds from `ffprobe -show_entries format=duration`):
   ```bash
   ffmpeg -y -i <name>.mp4 -vf "fps=14/D,scale=270:-2,tile=7x2:padding=6:margin=6" -frames:v 1 <name>-contact.png
   ```
   Open the PNG and look for type under 34 px, text outside the safe box, two things changing at once, a black or frozen frame, a claim the product cannot back. Fix and render again.

## Hard lines

- Free only: no paid generation, no cloud render, nothing that spends, unless the founder said yes to that exact run after a free price check (the Onca content guide says how).
- Real UI and demo data only; never the founder's real customer data, a password or a secret on screen.
- Work in a project folder of its own (one per concept); never write into this plugin's folders.
