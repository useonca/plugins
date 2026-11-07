# The edit timeline (`timeline.json`, version 1)

One JSON file describes the whole edit; `timeline.py render` turns it into one video per output size in one pass each. Times are seconds. Paths are relative to the timeline file.

```json
{"version": 1, "fps": 30,
 "sources": {"talk": "raw.mp4", "voice": "voice.wav", "ui": "clips/ui.mp4", "logo": "logo.png", "bed": "bed.m4a"},
 "audio_from": {"talk": "voice"},
 "main": [{"src": "talk", "in": 3.20, "out": 9.80}, {"src": "talk", "in": 12.00, "out": 20.50}],
 "overlays": [
   {"src": "ui", "in": 0, "out": 4.0, "at": 5.0, "layout": "full", "fade": 0.2},
   {"src": "@main", "at": 5.0, "dur": 4.0, "layout": "pip", "corner": "br", "scale": 0.28},
   {"src": "logo", "at": 13.0, "dur": 2.0, "layout": "box", "box": [0.40, 0.40, 0.20, 0.20], "fit": "contain"}],
 "audio": [{"src": "ui", "in": 0, "out": 4.0, "at": 5.0, "gain_db": -6}],
 "music": [{"src": "bed", "in": 0, "at": 0, "dur": 15.1, "gain_db": -18, "duck_db": 10, "fade_in": 1, "fade_out": 2}],
 "captions": {"words": {"talk": "words.json"}, "accent": "#FFC93C", "max_words": 4, "retext": {}},
 "outputs": [{"name": "16x9", "size": "1920x1080"},
             {"name": "9x16", "size": "1080x1920", "focus_x": 0.5, "mode": "auto", "band": {"top": 1150}}],
 "loudness": -16}
```

## Fields

- `sources`: name -> file. Videos, stills (`.png`, `.jpg`, `.webp`) and sound files.
- `main`: the spoken track, clips played back to back. `in` / `out` are times in the source. From an approved cut, one clip per `edl.json` range (`render.py` does exactly this). Its length is the video's length.
  - `zoom` (1 to 1.5): a punch-in on that clip, taken around `zoom_at` (`[x, y]` fractions, `[0.5, 0.35]` by default: faces sit above the middle). Change it only on a cut (a new shot anyway) or right before a sentence starts (split the clip there: a split with the same source and `out` = next `in` is no cut in the sound), at least 4 s after the last change, and sparingly: a jump in or out mid-sentence looks like a glitch (`verify.py`'s `zoom`).
- `audio_from`: the sound of a main source taken from another file on the same clock, usually the cleaned voice from `audio.py` (`"talk": "voice"`).
- `overlays`: drawn over the main track in order (later on top). `at` is the time on the output.
  - A video: `in` / `out` in its source. A still: `dur`.
  - `"src": "@main"`: the main track's own picture at that output time, with `at` + `dur` only. Use it to keep the speaker on screen as picture-in-picture while a full cutaway shows the product.
  - `layout`: `full` (the whole frame), `pip` (`corner` `tl` / `tr` / `bl` / `br`, `scale` = width as a fraction of the frame, 0.28 by default), `box` (`box` = `[x, y, w, h]` fractions of the frame).
  - `fit`: `cover` (fill and crop, the default) or `contain` (whole picture, centred) for `full` and `box`.
  - `fade`: seconds of fade in and out.
  - `per_output`: output name -> fields over this overlay in that output only (`layout`, `box`, `fit`, ...), or `{"hide": true}` to leave it out there. A wide product clip in a tall output: a `box` with `fit: contain` in the upper half, and the pip hidden, since the speaker shows below.
- `audio`: extra sound placed at `at` (a click, a clip's own sound), `gain_db`.
- `music`: a bed from `at` for `dur` (looped when shorter), `gain_db` (-18 sits under a voice), `fade_in` / `fade_out`, `duck_db` (how far it dips while someone speaks: 8 to 12). Use a bed with a licence you can name (made by the plugin, or one the founder owns); never paid generation without the founder's yes.
- `captions`: `words` maps a main source to its `words.json`; `accent` lights the spoken word; `max_words` per phrase; `retext` rewrites a caption word by index (as in `plan.json`). Omit `captions` for none.
- `outputs`: `name` (the file is `NAME.mp4`), `size`, and for the main track's reframe `focus_x` (0 left, 1 right: where the subject sits when cropping to a narrower frame) and `mode` (`auto`, `crop`, `fit`); `band` moves the caption band (`top`, `left`, `width`, `height` in pixels).
- `loudness`: the target in LUFS (-16 for social).

## Patterns

- One camera: a cutaway or a punch-in at a sentence start when a shot has held still a long while; a talking face may hold up to 12 s (`verify.py`'s `still`).
- Speaker, then the product: a `full` cutaway of a `screen-demo` recording over the words that describe it, with `@main` as a `pip` so the speaker stays.
- A title or end card: a still or a rendered card as a `full` overlay for its seconds, or a main clip of its own.
- Several takes or cameras: each file in `sources`, clips from any of them in `main`.

`timeline.py check` lists every problem at once (unknown source, `out` not after `in`, a clip past its source's end, an overlay past the main track's end, a bad layout, a duplicate output name). `timeline.py words` writes the kept words on the output clock (what the captions and `verify.py --timeline` use).
