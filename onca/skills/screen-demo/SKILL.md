---
name: screen-demo
description: Onca production kit. Make polished product footage yourself, end to end, with no founder step - rebuild the product's screens from its source and animate them, or record the running web app in a headless browser - then polish any footage with an auto zoom to each click, a smoothed enlarged cursor, a styled stage and motion blur, and build long chaptered, narrated 16:9 demos for YouTube with captions. Free and local on the founder's Mac. Use when a video needs product footage, a screen recording, a demo, a walkthrough, a product tour, a YouTube demo or tutorial, or when a client is about to ask the founder to record, stage or type demo data.
---

# Screen demo (Onca production kit)

You make the footage. The founder never records, stages, types demo data or edits; the founder only approves what you show them. Everything renders on the founder's Mac for free through Onca's render engine (the `video-render` skill). Never run a paid service from this skill.

Paths below are relative to this skill's folder; run each script by its absolute path, with `python3` (macOS's own 3.9 works).

## The footage ladder

Pick the lowest rung that shows the product truthfully, and say in your report which rung you used and why.

0. **Reuse what the project already renders**: its marketing site's live pages, Storybook or component previews, snapshot-test images, design files. Cheapest when it exists.
1. **Rebuild from source (the default)**: read the views, theme values, copy, states, animations and timings, rebuild the screens in HTML with the kit, script the flow, render it. No launch, no permission, no founder step, any stack (web, native, mobile). Details: `references/rebuild.md`.
2. **Capture the running product** only when it adds something the rebuild cannot (a live animation, real data volume) and the project's rules allow running it. Web: `scripts/record.py` (headless browser, its own profile). Native: build from source and run it in a sandboxed data container with UI automation and `screencapture`, or `xcrun simctl io booted recordVideo` for a simulator. A one-time OS permission is asked once, with its reason, and only on this rung.

Hard lines:
- Demo data never touches the founder's real app data, accounts, keychain or memory. Use a sandbox data folder or a fresh profile, and say where.
- Follow the project's own rules (its CLAUDE.md, what may be run or installed). When a rung would break one, take a lower rung instead of asking to relax the rule.
- A rebuilt screen is real UI only when built from the product's real values, copy and behavior. Invent nothing on the product's own surfaces; demo records (names, emails) are the only invented data, and say so.
- Product UI stays flat: never tilt it into 3D.

## Every rung writes the same REC folder

`REC/raw.mp4` (the footage) and `REC/clicks.json` (`{"viewport": {"w", "h", "dpr"}, "duration", "events": [{"t", "kind", "x", "y"}]}`, kinds `click`, `tap`, `key`, `move`, `scroll`, positions in CSS pixels of the source). `scripts/polish.py` turns any REC into a finished clip, so a native capture only has to write these two files.

## Rung 1: rebuild and play a flow

1. `python3 scripts/tokens.py SRC --out tokens.json`: the product's colours (colour sets, Swift colours, CSS custom properties), fonts (CSS, Swift `.custom`, bundled font files) and copy (`.xcstrings`, `.strings`). It only reads.
2. Write `FLOW_DIR/index.html`: its `<body>` holds every screen, each an element with `data-screen="id"`, at the product's logical size, styled with the real tokens and the kit's chrome classes (`assets/kit/kit.css`: `mac-desktop`, `mac-menubar`, `mac-notch`, `mac-window`, `mac-titlebar`, `mac-lights`, `mac-panel`, `ios-frame`, `ios-status`, `ios-island`, `ios-home`, `browser-frame`, `browser-bar`, `browser-url`, `browser-body`). Add `<div id="onca-keys"></div>` for a keystroke overlay. Keep a `SOURCE.md` beside it: each value and the file and line it came from.
3. Write `FLOW_DIR/flow.json`: `{"size": "1440x900", "pointer": "arrow" | "finger", "screens": [ids], "start": id, "steps": [...]}`. Steps, each with an optional `"pause"` (seconds after it, default 0.8):
   - `{"show": id}` switches screen (0.25 s fade);
   - `{"click": css, "then": action}` and `{"tap": css, "then": action}` press for 0.15 s, then apply one `show` or `set` action;
   - `{"type": text, "into": css, "cps": 14}` types into a field;
   - `{"set": css, "text" | "add" | "remove" | "attr": ...}` changes text, classes or attributes;
   - `{"key": label, "at": css, "then": action}` a keyboard press: shows the label in `#onca-keys`, and with `at` the camera follows that element;
   - `{"wait": seconds}`.
4. `python3 scripts/flow.py render FLOW_DIR --out REC [--dpr 2] [--draft]`: copies the kit in, measures each pressed target in a headless browser and renders `REC/raw.mp4` at 2x for sharp zooms. The cursor and camera are added by the polish, not drawn in the page.

## Rung 2 (web): record

`python3 scripts/record.py run steps.json --out REC [--size 1440x900] [--dpr 2]`. Steps: `{"goto": url}`, `{"click": css | [x, y]}`, `{"type": text, "into": css}`, `{"scroll": dy, "at": [x, y]}`, `{"wait": s}`, `{"key": "Enter"}`, each with an optional `"pause"`. It opens its own headless browser with a throwaway profile (never the founder's), moves a real mouse path, and records the browser's own screencast at 30 fps. Typed text never reaches a log. A local dev server's certificate is accepted for localhost only. Never submit a real form (sign-ups, waitlists, payments) in a recording. Record a production build (`npm run build && npm start`) or the live URL, never a dev server: the recorder hides known framework dev badges and overlays and stops (exit 1, naming it) when one still shows. A scroll step moves only as far as the page can scroll and is skipped when the page has under 40 px of room, so a page that does not scroll never shudders on video.

`record.py capture --port P --out REC [--seconds 20]` records a browser that is already open with a debugging port, for example one a browser-automation session drives.

## Polish

`python3 scripts/polish.py REC --out clip.mp4 [--size 1920x1080 | 1080x1920] [--zoom 1.8] [--no-zoom] [--pointer arrow|finger] [--background '#151412,#3A3326'] [--draft]`

It puts the footage on a padded, rounded, shadowed stage over a two-colour gradient (use the brand's colours when known), zooms in 0.45 s before each burst of presses and eases out a second after, glides an enlarged cursor (a finger dot for mobile) and rings each press. A 9:16 size keeps a base zoom so the screen fills the frame. It writes `clip-hf/` (the project and its `check.json`), a silent `clip.mp4` and `clip-contact.png`. Look at the contact sheet before showing anyone: text readable at the zoom, the cursor where the action is, nothing cut off.

## Long demos (YouTube)

Plan, voice and build a chaptered 16:9 demo: `references/long-demo.md`. In short: write `STORYBOARD.md` and `demo.json`, run `voice/scripts/say.py --storyboard demo.json --out voice` (the built-in voice), then `python3 scripts/demo.py build demo.json --out DIR [--burn-captions] [--draft]`. It writes the video, `chapters.txt` for the description, and `captions.srt` and `captions.vtt` to upload. Type: `demo.json` takes `"fonts": {"display": ..., "text": ...}` from the brand kit, else `"tone"` (`modern`, `friendly`, `editorial`, `technical`, `warm`) picks an open-licence pairing; titles are balanced with no lone last word and curly quotes, and the build stops when a font did not load.

## Templates and other skills

- Onca's templates `walkthrough` and `product-demo` (`get_template`) give the structure; this skill gives the footage.
- Photo and code-made b-roll between product shots: the `b-roll` skill.
- Short vertical launch videos: the `launch-video` skill, with footage from here.
- Narration: the `voice` skill. Captions on a talking video: `video-edit`.

## Errors

Every script exits 2 for bad input (one problem per line on stderr) and 1 when a tool failed (its last output shown). `record.py` without a browser says `no Chrome found: install Google Chrome`.
