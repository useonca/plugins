# The 14 parts

A cue is `{"id", "part", "at", "dur"?, "params"?, "snap"?, "sfx"?}` in `cues.json`. `id` is an element in `index.html`, `at` the start in seconds or a word of the voice (`{"line": "hook", "word": 3, "offset"?: -0.1}`: that word's start in `words.json` from `kit.py voice`, word 1 the line's first; such a cue never snaps), `dur` the length (each part has its own default), `snap` is `beat` or `bar` (moved to the nearest one within 0.15 s, only when the bed's beat is clear), `sfx` the effect names (left out: the part's own effect; `[]`: none).

How every part works:

- The part owns the element's `opacity`, `transform` and `filter`. Place the element with `left`, `top`, `width` and `height` in your CSS; a `transform` or `rotate` you put in CSS is overwritten, so a tilt goes in the part's `rotate` param.
- Before its `at` an element shows its first frame (usually hidden); after its `dur` it holds its last frame. An element with two cues runs every one that has started, in order: the latest wins what they share (opacity, position, scale), so a `move` after a `pop` takes over at its own `at`, while a counter's digits or a headline's words stay as the earlier cue left them.
- Default lengths are tuned to the reference moments; change `dur` or the part's timing params before writing your own motion.
- Easing names: `linear`, `outCubic`, `outQuart`, `outExpo`, `inCubic`, `inOutQuad`. Springs are `spring(t, damping, freq)`: damping under 1 overshoots and settles, 1 never overshoots.

## words

Headline word by word. Params: `text` (else the element's own text), `mode` `ink` (grey to ink, the default), `blur`, `rise` or `pop`; `gap` 0.08 s between words; `accent` word positions from 0 (`[3]` lights the fourth word); `from_voice` true takes each word's time from the voice.

- Copies: a hook headline whose words darken one after another as they are said.
- Timing: `gap` 0.08 to 0.15 s reads as fast speech; with a voice use `from_voice` so the word lands as it is said. Hold the full line at least 1 s after the last word.
- Layering: on its own over a calm ground; the highlight box goes over it after the line has landed.
- Do: one accent word, the number or the promise. Don't: accent more than two words, or use `pop` on a long line (it reads as jitter).

## highlight

An accent box with corner handles, an ellipse drawn round, or a marker swipe. Params: `style` `box`, `ellipse` or `marker`; `draw` 0.35 s; `pad` 12; `handles` true. Effect: a pop as the draw finishes.

- Copies: the selection box that snaps round the key number, the circle drawn round a word.
- The element is an empty box you size and place over the words it marks (it is allowed to cover them).
- Timing: start it 0.2 to 0.4 s after the words it marks have landed. Keep `draw` 0.25 to 0.45 s.
- Do: one highlight on screen at a time. Don't: highlight before the viewer has read the words.

## captions

Word captions on the voice, a few words at a time, the spoken word lit. Params: `max_words` 4; `max_chars` 24; `style` `box` or `plain`; `from_voice` true (its default). The words come from the `words` file named in `cues.json`. A chunk never runs across a voice line's or a sentence's end; inside one, chunks are grouped as `video-edit`'s captions are: a chunk ends at a clause's end (`, ; :`) or a pause, a short comma phrase joins the next, and a long phrase is cut into even pieces of at most `max_words` and `max_chars`.

- Copies: bold captions in the lower middle that change with each phrase.
- Placement: inside the 80% title-safe box, never over the product's name, a face or a number. The `box` style sits on its own ink plate, so the bottom third stays as full as the rest of the frame: clutter, props and the edges of cut-outs may sit under the captions (they are above every scene); keep only the hero's words out from under them.
- Timing: chunks break on the voice's phrases; keep `max_words` 3 to 5.
- Do: let the voice decide the times, and keep the captions element outside every scene (a direct child of `#main`, above the scenes) so a scene change never moves it; the part keeps it out of the engine's motion blur. Don't: run captions and a `words` headline saying the same thing at once.

## odometer

A rolling counter: each digit column rolls from its start digit to its end digit, right to left. Params: `to` (required), `from` 0, `format` `comma` or `plain`, `prefix`, `suffix`, `tiles` false (each digit on its own tile), `stagger` 0.05. Length 1.4 s. Effects: a tick as it starts and as it lands.

- Copies: a view count or revenue figure rolling up to its final value.
- Timing: 1.2 to 1.8 s; snap the end to a beat when there is music (`"snap": "beat"`).
- Layering: large, alone, with a one-word label under it.
- Do: real numbers the product can back. Don't: roll a number with more than 9 digits, or two counters at once.

## card-grid

A 3D tilted grid of cards with a wave running through it from one card. Params: `rows` 6, `cols` 5, `tilt` 55 degrees, `wave_from` `[row, col]`, `wave_speed` 8 (cards per second), `lift` 40 px. Cards it does not find it makes; put your own `.om-card` children (screenshots in an image tag) first.

- Copies: a wall of tilted thumbnails with a ripple of light passing through them.
- Timing: the wave crosses in about 1 s; start it as the voice names the many things.
- Layering: a background beat; the message card sits over it, flat and sharp.
- Do: start the wave from the card nearest the message. Don't: put text you need read inside the tilted cards.

## pop

A pop-in at a tilt, on a spring. Params: `from_scale` 0.6, `rotate` 0 (the resting tilt), `rotate_from` -8, `damping` 0.6, `freq` 3.2, `each` (a `.class` or tag: every matching child pops in turn), `stagger` 0.06 s. Effect: a pop for each item.

- Copies: stickers, cut-out products and labels popping onto the collage.
- Timing: `stagger` 0.12 to 0.2 s for 3 to 5 items so each pop is heard; keep `damping` 0.5 to 0.7.
- Do: give each item its own small resting tilt (-6 to 6 degrees). Don't: pop more than 6 things in one cue.

## drop

A label, pin, clip or tape slapped on: falls from a little large and lands with its shadow. Params: `from_scale` 1.25, `rotate` 0. Length 0.28 s. Effect: a tap as it lands.

- Copies: a torn paper label or a pin pressed onto the board.
- Timing: 0.22 to 0.35 s; drops after the thing they fix in place.
- Do: drop the pin a beat after the note it holds. Don't: drop more than three things in a row.

## move

A slide, stack or whip from one place to another. Params: `from` and `to` (any of `opacity`, `x`, `y`, `scale`, `rotate`, `blur`; x and y in px from where the CSS puts it), `ease` `outExpo`. Length 0.6 s. Effect: a whoosh when it lasts 0.45 s or less and travels 300 px or more.

- Copies: a card whipping in from the side, a stack sliding up.
- Timing: whips 0.3 to 0.45 s with `outExpo` (the engine adds motion blur to fast moves); calm slides 0.6 to 1 s with `outCubic`.
- Do: move toward where the eye goes next. Don't: move two large things in different directions at once.

## chart

A line or bars drawing in, then the label. Params: `kind` `line` or `bars`, `values` (numbers), `label`, `draw` 1.0 s. Effect: a pop as the draw finishes.

- Copies: a growth line drawing left to right with a dot riding its tip.
- Timing: `draw` 0.8 to 1.4 s; the voice says the result as the line lands.
- Do: few points (4 to 8), the last one the highest when that is true. Don't: axes, grids or a legend: the label is the message.

## focus

A focus pull: blur to sharp (`direction` `in`) or sharp to blur (`out`), with a slight settle in scale. Params: `from_blur` 18 px, `from_scale` 1.06. Length 0.6 s.

- Copies: a scene that opens blurred and snaps sharp, or blurs out behind a new message.
- Timing: 0.4 to 0.8 s. Use `out` on the background as the next message enters.
- Don't: blur the product UI while it is the subject.

## spotlight

A full-frame stage: a dark ground lit by a cone from above, which may flip to a light one. Params: `mode` `dark` or `light`, `cone_x` 0.5, `cone_w` 0.5, `flip_at` (seconds, or null). Effect: a whoosh at the flip.

- Copies: a dark reveal stage that flips to a bright one as the answer arrives.
- The element covers the frame and sits behind everything else.
- Timing: light up over 0.8 s; flip as the voice turns from problem to answer.
- Do: one flip per video. Don't: put grey text on the dark stage (check contrast).

## bubble

A chat bubble: typing dots, then the message, with a small pop as it lands. Params: `side` `in` (grey) or `out` (accent), `text`, `typing` 0.9 s. Effect: received (in) or sent (out) as the message lands.

- Copies: a message thread building up, one bubble after another.
- Timing: `typing` 0.6 to 1.2 s; 0.3 to 0.6 s between bubbles. Short messages, one line when possible.
- Layering: stack bubbles in a column; a new bubble pushes the old ones up with a `move` on the column.
- Do: the tail props (`bubble-tail-in`, `bubble-tail-out`) for a phone look. Don't: more than five bubbles on screen.

## morph

One shape into the next: size, corner radius and colour move together, with a stretch and a blur at the fastest moment; each state's content fades in as the last one's fades out. Params: `states` (each `{at, w, h, radius, bg, show}`: `at` seconds from the cue, `show` the id or ids of the children to show), `dur` 0.35 s per change, `stretch` 0.12, `blur` 12. Effect: a short whoosh at each change.

- Copies: a bubble turning into an app icon, then a loading pill, then a status card.
- The element is centred and holds one child per state, each with its own id.
- Timing: 0.6 to 0.9 s between states, `dur` 0.3 to 0.45 s.
- Do: change one or two of size, radius and colour per step, and keep the content simple. Don't: morph between shapes whose content needs reading in under 0.6 s.

## scene

A scene change. Each scene is a full-frame element (`.om-scene` is added for you), later scenes above earlier ones in the page; the cue goes on the incoming scene. Params: `kind` `cut` (a hard cut), `slide` (a paper sheet slides over, 0.6 s), `whip` (a fast slide the engine smears, 0.35 s) or `tear` (revealed behind a torn edge, 0.55 s); `from` `left`, `right`, `up` or `down`; `out` the outgoing scene's id (hidden once the change is over); `seed` the tear's edge. Effects: a whoosh on a whip, a short whoosh on a slide or tear, none on a cut.

- Copies: the collage story's jumps from the cutting mat to a new paper colour while the caption runs on.
- Convention: one kind per video, used at every beat change; a `cut` on the voice's new sentence, a `slide` or `tear` between chapters, a `whip` only into the payoff.
- Layering: captions, the logo bug and anything that stays across scenes sit outside the scenes, above them.
- Don't: change scenes in the middle of a line, or more often than every 1.5 s.

