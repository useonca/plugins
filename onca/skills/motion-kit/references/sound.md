# Sound: effects, beats and the music bed

The voice carries the video, the music sets the pace, the effects mark what moves. Mix order of importance: voice, then effects, then music (the bed sits about 18 dB under the voice and ducks under it).

## Effects

The pack in `assets/sfx/` (48 kHz mono WAV, several takes of the common ones so repeats do not sound robotic):

| Name | Takes | Sounds like | The kit uses it for |
|---|---|---|---|
| `whoosh` | 3 | air past the camera | a fast `move`, the `spotlight` flip |
| `whoosh-short` | 2 | a quick swish | each `morph` change |
| `pop` | 3 | a soft pluck | `pop` items, a `highlight` or `chart` landing |
| `tick` | 2 | a small click | an `odometer` starting and landing |
| `key` | 2 | one key press | typing on screen, one per word at most |
| `typing` | 1 | a burst of keys | a typed line |
| `sent` | 1 | a rising blip | an `out` bubble |
| `received` | 1 | a soft chime | an `in` bubble |
| `notification` | 1 | a bright chime | a status card or alert arriving |
| `tap` | 2 | a soft knock | a `drop` landing |
| `riser` | 1 | a rising swell | before a reveal, ending on it |
| `impact` | 1 | a low hit | the reveal itself, once per video |

- Each part sounds at its own moments (`references/parts.md`); a cue's `sfx` list renames them (`["tap"]`), `[]` silences it, and a part with no sound of its own sounds once at its `at` when given a list.
- The tool keeps the earlier of two effects closer than 0.12 s, rotates the takes in time order, and places each so its peak lands one frame after the motion it marks.
- Founder's position: every effect is CC0 (Kenney, OpenGameArt pages that say CC0), so it is free for commercial posts and ads with no credit; sources and dates are in `assets/LICENSES.json`.

Run it after a render: `PY scripts/kit.py sound PROJECT --video RENDER.mp4 [--voice VOICE.wav] [--music BED] [--music-db -18]`. It writes `PROJECT/timeline.json` (a `video-edit` timeline) and renders `PROJECT/out/with-sound.mp4` at -16 LUFS through `video-edit`'s `timeline.py`. `--no-render` writes the timeline only. The render runs the same on Windows (`video-edit`'s `timeline.py` finds ffmpeg and the computer's hardware encoder there).

## Beats

`PY scripts/kit.py beats PROJECT --music BED` reads the bed's beats with the render engine and writes `beats.json` (`bpm`, `bpmConfidence`, `beatTimes`, `bars`, a bar being every 4th beat). Then each cue marked `"snap": "beat"` or `"snap": "bar"` moves to the nearest one at `sync`, at most 0.15 s; a cue further off keeps its time, and nothing moves when the beat confidence is under 0.5 (a note says so).

- Snap the moments that should hit: a counter landing, a reveal, a whip, a cut. Leave words on the voice.
- A bar is 4 beats; scene changes on bars feel calm, on beats feel fast.

## The music bed (Higgsfield only, the founder approves each run)

Music beds come only from Higgsfield's audio models, reached through Onca's gateway, paid in the founder's Higgsfield credits.

1. Call `list_services`. With no Higgsfield connection, deliver the video without music and tell the founder: "Connect Higgsfield to add a music bed: connect_account with platform higgsfield."
2. Pick the model: `elevenlabs_music_v2_5` by default (instrumental, licensed training data), `sonilo_music` when the founder wants it cheaper. Never `seed_audio` or the `suno_*` models for music: their training data is undisclosed or in open lawsuits.
3. Build the call: `PY scripts/kit.py music params --prompt "warm lo-fi, 92 bpm, no vocals" --seconds 30 [--model sonilo_music]` prints the `params` for `higgsfield_generate_audio`; `--price-check` adds the free price check.
4. Price it with the price check, show the founder what will be made, the model, the length and the credit cost, and run it only after their yes for that exact run. A retry or a second version needs a new yes.
5. Wait with `higgsfield_jobs_wait`, download the file, save it to the library with `library_add` (pass the gateway call id) when the founder wants it kept.
6. Record it: `PY scripts/kit.py music record PROJECT --file BED --model M --prompt TEXT --seconds S --credits C --job JOB [--call CALL_ID]` copies the bed into `PROJECT/music/` and writes `PROJECT/music.json` (model, prompt, credits, job, the terms link and the founder's position). Keep it next to the video.

Founder's position: Higgsfield allows commercial use of the output (its terms, section 4.4) but does not clear rights (section 13.2). The `music.json` record is the founder's proof of where the bed came from.

- Prompt for a bed, not a song: genre, mood, tempo in bpm, "instrumental, no vocals", and a length a little longer than the video.
- Never add music from anywhere else (a download, a track the founder names, a platform's library): platform sounds are added in the platform's own app at post time.
