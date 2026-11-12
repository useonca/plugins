---
name: b-roll
description: Onca production kit. Make b-roll for product videos, free and local - turn a still photo into a moving shot with Onca's parallax (a depth map plus Onca's own shader) or a pan and zoom, and build code-made depth scenes (parallax layers, depth of field, lit 3D with glow) - and decide where b-roll goes in a video, how often and from which source. Use when a video needs cutaways, b-roll, a moving photo, a 2.5D or parallax shot, an establishing shot, or a break between product screens.
---

# B-roll (Onca production kit)

B-roll is the footage between product shots: it gives the eye a rest, sets a place or a mood, and shows what the product is for. Everything here renders on the founder's computer for free through Onca's render engine (the `video-render` skill).

Paths below are relative to this skill's folder; run each script by its absolute path with `PY` (`python3` on a Mac, `py -3 -X utf8` on Windows).

## Where b-roll comes from (in this order)

1. **The product's own footage**: a polished clip or a zoomed detail from the `screen-demo` skill.
2. **Code-made scenes**: shapes, type, charts and depth scenes built in HTML (`references/depth-kit.md`).
3. **The founder's own photos** (an office, a workshop, the team at work, with the people's agreement), moved with `scripts/broll.py`. A free licence photo (CC0 or public domain) when the founder has none, with its page named in the notes.
4. **Paid generation last**: only when nothing above can show it, after a free price check shown to the founder and the founder's yes for that exact run. Never AI-made people.

## Photo to clip

`PY scripts/broll.py photo IMG --out clip.mp4 [--seconds 5] [--move dolly|orbit|pan-left|pan-right] [--size 1920x1080] [--engine parallax|kenburns] [--depth depth.png] [--draft]`

- **Parallax** (default): makes a depth map of the photo (`scripts/depth_map.py`, a small free depth model) and moves a virtual camera through it with Onca's own shader, so near things slide against far ones. The depth map needs free tools that `uv` downloads once (about 800 MB, cached afterwards). Tell the founder and ask once before the first run; `--depth` reuses a map made earlier.
- **Pan and zoom** (`--engine kenburns`, moves `in`, `out`, `left`, `right`): ffmpeg only, no download. Use it when `uv` is missing, the founder declines the download, or the photo has no clear depth (a flat wall, a screenshot).
- It writes `clip.mp4` (silent, 30 fps) and `clip-contact.png`; parallax also keeps `clip-depth.png` and the project `clip-hf/`. Look at the contact sheet: tearing at the edges of near objects means the move is too strong; use a shorter or calmer move.

Product UI never goes through the parallax and is never tilted into 3D: it stays flat and sharp.

## Cutting b-roll in (practitioner opinion, not platform rules)

- Between product beats, not in the middle of one: after a result lands, before the next task starts.
- Each b-roll shot lasts 2 to 5 seconds; in a long demo something should change on screen every 4 to 8 seconds.
- Keep it on topic: the place the product is used, the problem it solves, the result. Decoration with no reason reads as filler.
- Narration may run over b-roll; captions stay where they were.
- Match the move to the cut: a push in before a zoom into the product, a sideways move into a sideways transition.

## Other skills

- Footage and long demos: `screen-demo`. Short vertical launch videos: `launch-video`. Narration: `voice`.

## Windows

`broll.py` runs the same way on Windows 11 (x64): the pan and zoom route needs only ffmpeg; the parallax depth map downloads its free tools through `uv` once (the same 800 MB, a CPU build of the model on Windows, so it takes a little longer). Install with the `video-render` skill's `## Windows` steps. Written from the tools' documentation and not yet run on a Windows machine: say which step failed if one does. Commands: one per line, no `&&`, no `\` line breaks.
