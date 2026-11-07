---
name: voice
description: Narration for a launch video, three ways the founder picks from - the free built-in voice on an Apple Silicon Mac, the founder's own voice cloned on their Mac (only from their recording, with their consent in words), or Onca voice (30 studio voices made by Onca, paid in Onca credits after the founder approves the cost). Use when a video needs a voiceover or a spoken line. Never another person's voice.
---

# Voice

Three ways to narrate. Offer all three and let the founder pick; none is pushed first.

| Option | Cost | Where it runs | Voices |
|---|---|---|---|
| Built-in local voice | free | the founder's Mac (Apple Silicon) | one built-in voice |
| The founder's own voice | free | the founder's Mac (Apple Silicon) | cloned from the founder's recording, with consent |
| Onca voice | Onca credits, approved by the founder each time | Onca | 30 voices, with a style line and tags |

If the project's brand kit has a `narrator` (`get_brand_kit`), the founder once picked that Onca voice: name it as the Onca voice option, and still offer all three.

Paths below are from this skill's folder (the folder this SKILL.md is in): run each as that folder's absolute path plus the path, because commands run from the video's own folder.

## Whose voice

- Never clone another person's voice, a celebrity's, a generated presenter's or a voice from a found clip, whatever the reason. No AI people in Onca videos, and that includes their voices.
- The founder's own voice: only from a recording of the founder's own voice that the founder gives for this purpose. Ask first, in words: "Do you want the narration in your own voice? If yes, send a clean 10 to 20 second recording of you speaking, and confirm it is your voice and that you agree to it being cloned for this video." Go on only after a clear yes and their file.
- Onca voice and the built-in voice need no recording and no consent step.

## Local: the built-in voice or the founder's own

Narration runs on the founder's Mac with Chatterbox (`mlx-community/chatterbox-fp16`) through mlx-audio. It is free; the first run downloads the model.

- Apple Silicon only. Check with `python3 ../video-render/scripts/doctor.py check`: `mlx_audio.tts.generate` must be there. Missing: show the founder `uv tool install mlx-audio` and run it only after their yes.
- Model licences (read from the model cards): `mlx-community/chatterbox-fp16` is Apache 2.0 (https://huggingface.co/mlx-community/chatterbox-fp16), converted from Resemble AI's Chatterbox, MIT (https://huggingface.co/ResembleAI/chatterbox). Both allow commercial use. Every line Chatterbox speaks carries Resemble AI's PerTh watermark, an inaudible mark that identifies it as generated audio; say so if the founder asks, and never try to remove it.

```bash
python3 scripts/say.py --text "Your whole clipboard, kept." --out voice-out --prefix line1
python3 scripts/say.py --text "..." --out voice-out --prefix line1 --ref founder-voice.wav   # the founder's own voice
```

- Write product names as they are said, in a phonetic spelling (for example `Acme` as `Ak-mee`), and read the output names back to check.
- `--exaggeration 0.5` is the start value; raise it toward 0.7 for more energy, lower it toward 0.3 for calm. Keep 0 to 1.
- One WAV per call (`voice-out/<prefix>.wav`). Make one line per scene, so each can be timed to its scene.
- A long demo's storyboard in one go: `python3 scripts/say.py --storyboard demo.json --out voice` speaks every scene's `say` into `voice/<scene id>.wav` (blank lines skipped), the files the `screen-demo` skill's `demo.py` reads. `--ref` works the same way for the founder's own voice.

## Onca voice

Onca makes the speech on its own account and charges Onca credits; the founder approves each voiceover with its exact cost before anything is made. Samples are free.

1. `list_voices` shows the 30 voices, the narrator, the free samples left today, the price and the tags.
2. `sample_voices(text, voices?, gender?, style?)` plays one line (up to 200 characters, ideally from the script) in up to 6 voices, free (a day allows a set number of new sample files, `samples_left_today`; a repeat of the same voice, style and line is served again at no cost). Give the founder `listen_at` (the Brand kit page, where they can also pick), or play the files for them. Save the founder's pick with `update_brand_kit(narrator={voice, style})`.
3. `make_voiceover(lines, voice?, style?)`: one `{id, text}` per scene (ids lowercase; for a `screen-demo` storyboard, the scene ids, so `demo.py` finds `voice/<scene id>.wav`), voice and style default to the narrator's. `dry_run: true` shows the cost first. The founder approves in a form, or on the Onca page the result names (`approve_at`, open for 1 hour); then call again with the `approval_id` it gave and the same lines, voice and style (any change is a new voiceover the founder approves again). Onca makes an approved voiceover once.
4. The result's `download` line saves every line as `voice/{line id}.wav`: run it in the video's folder (for a storyboard, the folder `demo.py` runs in). The lines are in the founder's Library too.

- The text is read word for word. Delivery goes in `style` (for example "warm, confident, a little excited"), never in the text.
- Tags in the text mark a moment: `<laugh>`, `<short pause>` and the others `list_voices` lists. Use them sparingly.
- Write product names as they are said, like the local voice.
- A call takes at most 60 lines and 20,000 characters (a line at most 10,000); a longer script goes in several calls, each approved by the founder.
- Never call `make_voiceover` for a script the founder has not seen: it asks them to spend credits.

## Listen and place

- Listening is the founder's: you cannot hear the audio. Give them the files, ask them to listen, and fix the lines they flag.
- Place each line in the composition at its scene (the `hyperframes` skill's sound reference shows how), or mix with ffmpeg. In the editor, each WAV is a timeline `sources` entry placed with an `audio` entry at its scene (`video-edit` `references/timeline.md`).
- The finished video goes through the video-render skill's finish step, which sets loudness to -16 LUFS.
