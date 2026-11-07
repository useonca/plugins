# Long demos for YouTube

A chaptered 16:9 demo (1920 x 1080, 30 fps), narrated, with captions to upload. The structure follows Onca's `product-demo` or `walkthrough` template when the founder picked one (`get_template`), and the `youtube-demo` playbook (`get_playbook("youtube-demo")`).

## 1. Storyboard

Write `STORYBOARD.md` first and show it to the founder: a table of chapters with the start time, the chapter title, the script (the exact words) and the shots. Every claim is something the product does today, checked in its code or docs. Then write `demo.json`:

```json
{"title": "Product in 5 minutes", "size": "1920x1080", "chapters": [
  {"title": "Meet the product", "scenes": [
    {"id": "hook", "card": {"title": "One line that opens a question"}, "say": "What the voice says.", "min": 4},
    {"id": "tour", "clip": "clips/tour.mp4", "clip_from": 2.5, "say": "What the voice says over the clip."}
  ]}
]}
```

- `id`: lowercase letters, digits and hyphens, unique.
- Each scene has a `clip` (a polished clip from this skill, trimmed from `clip_from` seconds) or a `card` (a title, or `{"title", "text"}`).
- `say` is at most 600 characters; split longer narration into scenes.
- `min` is the scene's shortest length (default 2 s); a spoken scene lasts its voice plus 0.35 s each side.
- No em or en dash anywhere.

## 2. Voice

`python3 ../voice/scripts/say.py --storyboard demo.json --out voice` (from the skills folder) speaks every `say` in the built-in voice into `voice/<id>.wav`. Any WAV at a scene's `audio` path (default `voice/<id>.wav`) is used as is, so the founder's own recorded voice, given with their consent in words, drops in the same way. Never another person's voice.

## 3. Build

`python3 scripts/demo.py build demo.json --out DIR [--burn-captions] [--draft]` writes:

- `DIR/<name>.mp4` (H.264, yuv420p, 30 fps, loudness -16 LUFS);
- `DIR/chapters.txt`: the title and one `0:00 Title` line per chapter, for the video's description;
- `DIR/captions.srt` and `DIR/captions.vtt`: upload one as the video's captions (better than burning them in on YouTube; `--burn-captions` also draws them);
- `DIR/<name>-hf/` (the project, `timeline.json`, `check.json`) and a contact sheet.

It warns when the chapters break YouTube's rules: the first must start at 0:00, there must be at least 3, each at least 10 s long, in ascending order (YouTube Help 9884579). Fix the storyboard rather than ship without chapters.

## Craft (practitioner opinion, not platform rules)

- The first 3 seconds carry the hook; say what the viewer gets in the first sentence.
- Change the picture every 4 to 8 seconds in a long demo: a zoom, a new screen, a short b-roll shot (2 to 5 s, the `b-roll` skill).
- Captions on: many people watch muted.
- One music track at most, under the voice; the founder adds licensed music when posting.

## Sources

- YouTube Help, video chapters: https://support.google.com/youtube/answer/9884579
- YouTube Help, supported subtitle and caption files: https://support.google.com/youtube/answer/2734698
