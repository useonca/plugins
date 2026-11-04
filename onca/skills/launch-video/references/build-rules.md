# Build rules

For every video of every concept:

- 1080 x 1920, 30 fps, 15 to 25 seconds, H.264, loudness about -16 LUFS (the `video-render` contract). Words and key UI inside the safe box: x 120 to 940, y 220 to 1440 (a conservative working rule: 220 px top, 480 bottom, 140 right, 120 left; the platform's own templates are the final word). UI text 34 px or more on screen.
- Real UI only, never faked or almost-matching screens. Rebuild screens from the product's own markup and styles, or use real screenshots and recordings with demo data.
- Long ease-out motion, strong still titles, no bouncy springs, the logo at the end, a first frame that works as the thumbnail.
- One change at a time: only one text element changes on screen at any moment. A headline lands and is read before the next element changes. Give each headline and card its full read time (at most 5 to 10 words a second, plus a beat). A longer video beats one too quick to follow.
- Sound is part of the video: bundled or synthesized effects with a licence you can name; no copyrighted music or memes (draw a sticker instead). Narration, when used, comes from the `voice` skill.
- No stock faces, no pricing unless the founder asks, no em or en dashes, only true product claims, no wording that overclaims (say "kept the whole night" if the history is 30 days, not "forever").
- A passed engine check before every render: `sh "$ENGINE" check --json` in the project folder, `ENGINE` being the absolute path of the video-render skill's `scripts/engine`.
- AI video stays a minimum: at most a few seconds of a generated shot, only where nothing free can show it, and only after a free price check and the founder's yes for that exact run. Never a generated person.

## The shared brief

Write one `brief.md` before the builds start and give it to every build: the product facts and claims allowed, the brand (colours, fonts, logo file), the demo data, the screens to rebuild, the render contract above, and each concept's hook, info and closure. Every concept's folder holds its own composition and renders; nothing is shared but the brief and the assets.
