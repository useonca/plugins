# Depth kit: code-made depth for b-roll

Depth makes a flat video feel shot. Every effect here is drawn from the render engine's time (an `hf-seek` listener or a timeline), so any frame renders on its own. Product UI is never part of a depth effect: it stays flat, sharp and untilted.

## Parallax layers (2.5D)

Split a scene into 3 to 5 layers (background, middle, foreground, type) and move each by a share of one camera move: far layers 10 to 20%, the subject 50%, the foreground 100 to 130%. Ease the camera both ways over the whole shot; a 2 to 4% total move is enough at 1080p. For a photo, `scripts/broll.py` does this per pixel from a depth map instead of by hand.

## Depth of field

Blur by distance from a focus plane: the subject sharp, the rest `filter: blur()` of 2 to 8 px growing with distance. A rack focus moves the plane from one layer to another over about 0.6 s with an in-out ease; only one thing is sharp at a time.

## Lit 3D with glow and vignette

For an object or set as the payoff (never the product's UI): Three.js (MIT) in a canvas, drawn in the `hf-seek` listener from `e.detail.time`. A warm key light, a cool rim and a dark environment; bloom only on the brightest points; a soft vignette to hold the eye in the middle. The postprocessing library (Zlib) or its React wrapper (MIT) gives depth of field, bloom and vignette passes; drive their values from time too, never from their own clocks. Heavy setup (models, shader compiles) registers a `window.__hf.buildReady` promise.

## Motion blur

Set `data-motion-blur="on"` on the root (and `data-motion-blur-events="on"` when motion is set from a seek callback) so fast moves smear along their path, as a camera would.

## Rules

- Product UI is flat: depth goes around it, never on it.
- No AI-made people, no stock faces.
- Everything renders locally; a paid generated shot is the last resort (see the `b-roll` skill).

## Sources

- Onca's render engine, motion blur and runtimes: the `hyperframes` skill, `references/motion.md` and `references/runtimes.md`.
- Depth Anything V2 (the Small model is Apache-2.0): https://github.com/DepthAnything/Depth-Anything-V2
- Three.js (MIT): https://github.com/mrdoob/three.js
- postprocessing (Zlib): https://github.com/pmndrs/postprocessing; react-postprocessing (MIT): https://github.com/pmndrs/react-postprocessing
- Screen Studio's guide to its animations (the zoom and cursor look the polish follows): https://screen.studio/guide/animations-motion
