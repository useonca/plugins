# Props, paper and fonts

Everything here is copied into the project's `kit/` by `kit.py new`, is free for commercial posts and ads, and is listed in `assets/LICENSES.json` (source, author, licence link, date). Add a file of your own only with a licence you can show in writing (CC0, or the founder's own); never a stock site's "free" licence.

## Props (`kit/props/NAME.svg`, drawn by Onca, CC0)

`sticky-note`, `polaroid`, `pin`, `binder-clip`, `paper-clip`, `tape`, `cutting-mat`, `bubble-tail-in`, `bubble-tail-out`, `sticker-star`, `sticker-heart`, `sticker-burst`, `sticker-arrow`, `sticker-smile`, `sticker-sparkle`.

- Use one as an image tag with an id: `<img id="pin1" class="om-prop" src="kit/props/pin.svg" style="left: 480px; top: 640px; width: 90px">`, then move it with `pop`, `drop` or `move`.
- Pins, clips and tape go on with `drop`, a beat after the thing they hold. Stickers go on with `pop`, each at its own small tilt.
- `cutting-mat` is a full-frame ground: an image tag with `inset: 0`, behind everything.

## Paper and collage pieces (classes in `kit/motion.css`)

- **Paper ground**: `<div class="om-paper" data-paper="white|kraft|card|crumpled"></div>` fills the frame with a photographed paper texture (ambientCG, CC0) tinted by the brand's `paper` colour. One ground per scene.
- **Torn label**: `<div id="label" class="om-torn" data-seed="3">Organic</div>`: a paper strip in the kit's serif (DM Serif Display, whatever the brand's display font; `"label_font"` in `brand.json` changes it) whose edges the runtime tears. A different `data-seed` tears it differently; `data-rough` (6) sets how jagged. Slap it on with `drop`.
- **Sticky note**: `<div id="note" class="om-sticky">one idea:</div>`, handwriting in Caveat; tilt it with the part's `rotate`.
- **Polaroid**: `<div id="shot" class="om-polaroid"><img src="product.png"></div>`, a white frame with a deep bottom edge; pop it in at a tilt.
- **Cut-out products**: `python3 scripts/kit.py cutout PHOTO OUT.png --trim` (Apple Vision on macOS 14+, else rembg with the open `isnet-general-use` model), then an image tag with `class="om-prop"`. Look at the edge before using it; a cut-out with a halo goes back to the founder's original photo.

## Product UI as a cut-out

- Never a 1x screenshot: its text lands at about a third of the size it needs and blurs. Rebuild the card or screen as a small HTML page from the app's own theme (colours, fonts, radius from its code or `get_brand_kit`), with real wording and demo data, or open the product's own page.
- Shoot it at 3x: `python3 scripts/kit.py shot card.html card.png --width 390 --height 844 --scale 3` (headless Chrome, a transparent ground, trimmed to the card). The log says the width to show it at.
- Show it at a third of its pixels inside a frame: `<div id="app1" class="om-cutout" style="left: 120px; top: 640px; width: 520px"><img src="card.png"></div>`, then `pop` or `drop` it on at a small tilt. UI text should land at 34 px or more on screen.

## Collage do and don't

- Dense, in layers, every beat: the ground (paper or the cutting mat), background clutter (a second paper scrap, tape strips, a torn edge, a few stickers half off the frame), one hero (the product, a cut-out photo or a UI cut-out, big), a torn label on it, and 2 to 4 props on top (a pin or clip holding something, a sticky note, a sticker). 5 to 9 pieces a scene, overlapping; little bare paper. Each layer enters after the one under it, all within the beat's first second: the ground and clutter are on at the beat's start (from frame 0 in the first), so no frame waits half empty for its pieces; a beat with one short line still gets its full set.
- Overlaps are intended: pieces cover each other's edges, never the hero's words.
- Don't place stickers over the product's name, a price or a face.

## Fonts (`kit/fonts/`, SIL Open Font License 1.1)

- **DM Serif Display**: the display serif for torn labels and collage headlines. **Caveat**: handwriting for notes and scribbles (`class="om-hand"`).
- Use them by name in `brand.json` (`"display_font": "DM Serif Display"`); they are declared in `kit/motion.css`. Torn labels keep DM Serif Display (`label_font`) when the brand sets its own display font.
- A brand font from the brand kit: `kit.py brand --fonts DIR` finds its file (the product repo, the system fonts) and names it in `brand.json`'s `font_files` (`{"Brand Sans": "fonts/BrandSans.woff2"}`); use only a font the founder owns or one under an open licence.
