---
name: voice
description: Narration for a launch video, three ways the founder picks from - the free built-in voice on the founder's Mac or Windows PC, the founder's own voice cloned on their computer (only from their recording, with their consent in words), or Onca voice (30 studio voices made by Onca, paid in Onca credits after the founder approves the cost). Use when a video needs a voiceover or a spoken line. Never another person's voice.
---

# Voice

Three ways to narrate. **Ask which voice, every video, before any voiceover.** Price the script first with `make_voiceover(lines, dry_run: true)` (free), then ask in plain words: "Onca voice sounds much more natural (costs N credits), or the free voice on your computer?" Then open the matching picker, where the founder plays each voice and clicks one; never list voices in chat. Onca voice: `sample_voices` (free) with a line of the script, open its `listen_at` page (the Brand kit's Narrator voice card: a grid of voice names, each with a small play button; a click on a name picks it) in the founder's browser, and read the pick back from `get_brand_kit` (`narrator`). The free voice: make a short sample of each local voice, list them in a `choices.json`, and run the `motion-kit` skill's `kit.py pick choices.json --out pick.json`, which opens the same kind of page on the founder's computer (only the names, a play button each, one click picks) and returns the pick.

| Option | Cost | Where it runs | Voices |
|---|---|---|---|
| Built-in local voice | free | the founder's Mac (Apple Silicon) or Windows PC | one built-in voice (Kokoro on Windows, which has more than one) |
| The founder's own voice | free | the founder's Mac (Apple Silicon); on Windows only with an NVIDIA graphics card (slow, not verified) | cloned from the founder's recording, with consent |
| Onca voice | Onca credits, approved by the founder each time | Onca | 30 voices, with a style line and tags |

If the project's brand kit has a `narrator` (`get_brand_kit`), the founder once picked that Onca voice: name it as the Onca voice option, and still offer all three.

`PY` is the Python command: `python3` on a Mac, `py -3 -X utf8` on Windows. Paths below are from this skill's folder (the folder this SKILL.md is in): run each as that folder's absolute path plus the path, because commands run from the video's own folder.

## Whose voice

- Never clone another person's voice, a celebrity's, a generated presenter's or a voice from a found clip, whatever the reason. No AI people in Onca videos, and that includes their voices.
- The founder's own voice: only from a recording of the founder's own voice that the founder gives for this purpose. Ask first, in words: "Do you want the narration in your own voice? If yes, send a clean 10 to 20 second recording of you speaking, and confirm it is your voice and that you agree to it being cloned for this video." Go on only after a clear yes and their file.
- Onca voice and the built-in voice need no recording and no consent step.

## Local: the built-in voice or the founder's own

Narration runs on the founder's computer. It is free; the first run downloads the model. `say.py` picks the engine: Chatterbox through mlx-audio on an Apple Silicon Mac, Kokoro on Windows and everything else, Chatterbox there only when `--ref` gives the founder's own voice.

- Mac (Apple Silicon): check with `PY ../video-render/scripts/doctor.py check` from this skill's folder: `mlx_audio.tts.generate` must be there. Missing: show the founder `uv tool install mlx-audio` and run it only after their yes.
- Windows: nothing to install beyond `uv` (`winget install --id=astral-sh.uv -e`, only after the founder's yes). `say.py` runs Kokoro through `uv run`, which fetches the packages and a 330 MB model the first time (a few minutes), then it speaks quickly on the CPU. The founder's own voice on Windows runs Chatterbox the same way: a few GB of model, slow without an NVIDIA graphics card, and its authors tested it on Linux, so tell the founder it is untested on Windows and offer Kokoro or Onca voice first. Windows on ARM: no local voice (the speech packages have no ARM Windows build); use Onca voice.
- Model licences (read from the model cards): `mlx-community/chatterbox-fp16` is Apache 2.0 (https://huggingface.co/mlx-community/chatterbox-fp16), converted from Resemble AI's Chatterbox, MIT (https://huggingface.co/ResembleAI/chatterbox). Kokoro-82M is Apache 2.0 (https://huggingface.co/hexgrad/Kokoro-82M) and its `kokoro-onnx` runner is MIT. All allow commercial use. Every line Chatterbox speaks carries Resemble AI's PerTh watermark, an inaudible mark that identifies it as generated audio; say so if the founder asks, and never try to remove it.

```
PY scripts/say.py --text "Your whole clipboard, kept." --out voice-out --prefix line1
PY scripts/say.py --text "..." --out voice-out --prefix line1 --ref founder-voice.wav
```

The second line is the founder's own voice. On Windows without `--ref`, `--voice af_heart` (the default) and `--speed 1.0` pick Kokoro's voice and pace (speed 0.5 to 2.0).

- Write product names as they are said, in a phonetic spelling (for example `Acme` as `Ak-mee`), and read the output names back to check.
- `--exaggeration 0.5` (Chatterbox only) is the start value; raise it toward 0.7 for more energy, lower it toward 0.3 for calm. Keep 0 to 1.
- One WAV per call (`voice-out/<prefix>.wav`). Make one line per scene, so each can be timed to its scene.
- A long demo's storyboard in one go: `PY scripts/say.py --storyboard demo.json --out voice` speaks every scene's `say` into `voice/<scene id>.wav` (blank lines skipped), the files the `screen-demo` skill's `demo.py` reads. `--ref` works the same way for the founder's own voice.

## Onca voice

Onca makes the speech on its own account and charges Onca credits; the founder approves each voiceover with its exact cost before anything is made. Samples are free.

1. `list_voices` shows the 30 voices, the narrator, the free samples left today, the price and the tags.
2. `sample_voices(text, voices?, gender?, style?)` plays one line (up to 200 characters, ideally from the script) in up to 6 voices, free (a day allows a set number of new sample files, `samples_left_today`; a repeat of the same voice, style and line is served again at no cost). Open `listen_at` (the Brand kit page, where the founder plays each voice and picks one) in the founder's browser; the pick is the brand kit's `narrator` (`get_brand_kit`). A pick the founder gives in words is saved with `update_brand_kit(narrator={voice, style})`.
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

## Windows

Local narration works on an x64 Windows PC through Kokoro (see above); it was written from the tools' documentation and not yet run on Windows, so say which step failed if one does. Commands: one per line, no `&&`, no `\` line breaks. Voice cloning is the hard part on Windows (Chatterbox is slow without an NVIDIA graphics card); Onca voice needs nothing installed.
