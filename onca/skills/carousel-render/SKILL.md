---
name: carousel-render
description: Onca's free local route for carousel slides and single post images (PNG) on the founder's Mac. Use it whenever an Onca template (get_template) asks for a carousel, a single image or a text card, or the founder wants slides for Instagram, LinkedIn-style posts, Threads, Bluesky or X. The slides are one HyperFrames composition, one scene per slide, snapshotted by the pinned engine of the video-render skill.
---

# Carousel render

Every slide is rendered locally and costs nothing: no image generation. Paths below are from this skill's folder (the folder this SKILL.md is in): run each as that folder's absolute path plus the path, because commands run from the carousel's own folder. `ENGINE` is the absolute path of the `video-render` skill's `scripts/engine` (this skill's folder plus `/../video-render/scripts/engine`); read the `video-render` skill once for its engine rules (never a cloud command) and its `doctor.py check`.

## Before you write

0. Onca's tools (templates, brand kit, Library) need the founder signed in: if they are missing or a call asks for sign-in, say so in plain words and give the sign-in steps from the `launch-video` skill's "Is Onca signed in?" section before working on without them.
1. `get_template` for the template the founder picked: its `Make it` section says the slides, the hook and the layout; its brief rule says what `schedule_post`'s brief must hold.
2. `get_brand_kit` for the project: use its colors, fonts, voice, logos and screens. Download each logo and screen you use with `library_get` (its `url`) into the carousel folder's `assets/`; never draw a logo or a product screen from memory. An empty kit: ask the founder for a logo and two colors, save them with `update_brand_kit`, then go on.
3. Make a folder of its own for this carousel (never inside this plugin) and work there.

## The composition

Write `index.html` as one still composition, one one-second scene per slide:

```html
<!doctype html>
<html><head><meta charset="utf-8"><style>
  html, body { margin: 0; }
  #root { position: relative; width: 1080px; height: 1350px; overflow: hidden; font-family: Inter; }
  .slide { position: absolute; inset: 0; }
</style></head><body>
<div id="root" data-composition-id="main" data-start="0" data-duration="3"
     data-width="1080" data-height="1350" data-no-timeline>
  <section id="s1" class="slide clip" data-start="0" data-duration="1" data-track-index="1">...</section>
  <section id="s2" class="slide clip" data-start="1" data-duration="1" data-track-index="1">...</section>
  <section id="s3" class="slide clip" data-start="2" data-duration="1" data-track-index="1">...</section>
</div></body></html>
```

- 1080 x 1350 (4:5) by default; 1080 x 1080 or 1080 x 1920 only when the founder or the platform asks. The root's `data-duration` is the number of slides.
- `data-no-timeline` and no script: the slides are still. Fonts: the `hyperframes` skill's bundled families resolve by name; any other needs `@font-face` with a file in `assets/`.
- Each slide carries one idea: a headline of 12 words or fewer at 64 px or more, body text at 34 px or more, everything at least 80 px from each edge. The first slide is the hook and works alone as the cover; the last says what to do next.
- Images by relative path (`assets/logo.png`), never a remote URL.

## Render and check

1. `sh "$ENGINE" check --json` in the folder; fix every error.
2. `python3 scripts/carousel.py times <slides>` prints the times, e.g. `0.5,1.5,2.5`.
3. `sh "$ENGINE" snapshot --at <those times>` writes the frames under `.hyperframes/artifacts/snapshots/`.
4. `python3 scripts/carousel.py collect . slides <name> --slides <slides>` (add `--size 1080x1080` for a square) copies them to `slides/<name>-01.png` onward and checks each size; exit 1 names what is missing.
5. Open each PNG and look for text under the sizes above, text near an edge, two ideas on one slide, a claim the product cannot back. Fix and render again.

## Save and post

- Save each slide with `library_upload` (service `onca`, model `Onca carousel`, the slide's text as the description), in slide order.
- Schedule with `schedule_post`: `media` is the library ids in order, `template` is the template id, and `brief` holds the full script, slide by slide, the caption and why this post, as the template's brief rule says.

## Hard lines

- Free only: no paid image generation for a slide unless the founder said yes to that exact run after a free price check.
- Real UI and demo data only; never the founder's real customer data, a password or a secret on a slide.
