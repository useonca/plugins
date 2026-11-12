# Make it like this video

When the founder shares a video they like, copy how it works, never what it shows: its pacing, layout, type and motion are free to learn from; its footage, music, brand, characters and words are not. The result uses the founder's product, words, brand kit and the kit's own licensed files.

## 1. Watch it

Use `video-edit`'s tools on the reference (its folder plus `/scripts`, as `S`):

```
PY S/transcribe.py REF.mp4 --out ref/words.json
PY S/map.py REF.mp4 --dir ref --words ref/words.json
```

(`S` is the folder's absolute path plus `/scripts`: write it out in each command.)

`ref/map.md` gives the words in phrases, each shot change with its time, words per minute and the longest still stretch; `ref/sheets/` one frame per shot. Zoom into the moments that move (`ffmpeg -ss T -t 2 -i REF.mp4 -vf fps=10,scale=360:-2,tile=5x4 ref/zoom-T.png`) to see how a part enters: what grows, what blurs, what overshoots.

## 2. Write the recipe

`recipe.json` describes the reference in the kit's words:

```json
{"version": 1, "source": "the founder's reference, 14 s", "duration": 14, "aspect": "9:16",
 "pace": {"shots": 9, "avg_shot": 1.5},
 "look": {"ground": "light grid, then a dark stage", "type": "heavy sans headline, one accent word",
          "accent": "one warm colour", "texture": "none", "density": "one hero per beat, 2 props"},
 "sound": {"voice": "fast, about 190 words per minute", "music_bpm": 120, "effects": "pops on numbers, whoosh on whips"},
 "beats": [
   {"from": 0, "to": 2.9, "says": "the hook question", "parts": ["words", "highlight"], "note": "words ink in on the voice"},
   {"from": 2.9, "to": 5.6, "says": "the problem", "parts": ["spotlight", "focus"], "note": "dark stage flips to light"},
   {"from": 5.6, "to": 9.0, "says": "the proof", "parts": ["odometer", "chart"], "note": "counter lands on a beat"}]}
```

- `beats` run in time order and do not overlap; each names what it says and the parts that build it (names from `references/parts.md`).
- `pace` and `sound` decide the edit: a reference at 1.5 s a shot means your video changes something every 1 to 2 s too.
- Write what you see, not what you guess: if the reference has no music, the recipe says so.
- `look.density`: count the pieces on screen at the busiest moment of a few beats (ground, clutter, hero, labels, props) and write it down; build to the same count. A collage reference usually has 6 to 10 overlapping pieces a beat: matching that does more than any one effect.
- Fill the frame from the first beat: count at each beat's first frame too, not only its busiest. A reference is rarely half empty while it waits for its hero, so the ground and clutter are on at the beat's start and the rest lands within its first second.

`PY scripts/kit.py recipe check RECIPE.json` lists every problem at once (exit 2).

## 3. Build from it

1. `PY scripts/kit.py new PROJECT --duration D` (D from the recipe), then the brand (`kit.py brand`).
2. `PY scripts/kit.py recipe cues RECIPE.json --out PROJECT/cues.json`: one cue per listed part, each at its beat's start, with placeholder values where a part needs them (a counter's `to`, a chart's `values`, a morph's `states`).
3. Write the founder's words for each beat (the `says` line tells you what each beat is for), the page's elements with the cue ids, and the real values; then time each cue inside its beat and `kit.py sync`.
4. Render a draft, set it beside the reference (`ffmpeg -i REF.mp4 -i draft.mp4 -filter_complex "[0:v]scale=1080:1920[a];[1:v]scale=1080:1920[b];[a][b]hstack" side.mp4`) and compare beat by beat: the same rhythm, the same kind of motion, your content. Fix the biggest difference first.

## What decides "pro"

- The rhythm: matching the reference's shot length and words per minute does more than any one effect.
- The type: one display face, one body face, big, tight, one accent colour.
- The motion's feel: springs where the reference overshoots, ease out where it glides; check it frame by frame on the zooms.
- The sound: effects only on the moments the reference marks, the bed at the reference's tempo.
