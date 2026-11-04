---
name: voice
description: Free local narration for a launch video with Chatterbox through mlx-audio on an Apple Silicon Mac. Use when a video needs a voiceover or a spoken line. The built-in voice by default; the founder's own voice only from a recording they give for this purpose, with their consent in words. Never another person's voice.
---

# Voice

Narration runs on the founder's Mac with Chatterbox (`mlx-community/chatterbox-fp16`) through mlx-audio. It is free; the first run downloads the model. Paths below are from this skill's folder (the folder this SKILL.md is in): run each as that folder's absolute path plus the path, because commands run from the video's own folder.

## Before the first line

- Apple Silicon only. Check with `python3 ../video-render/scripts/doctor.py check`: `mlx_audio.tts.generate` must be there. Missing: show the founder `uv tool install mlx-audio` and run it only after their yes.
- Model licences (read from the model cards): `mlx-community/chatterbox-fp16` is Apache 2.0 (https://huggingface.co/mlx-community/chatterbox-fp16), converted from Resemble AI's Chatterbox, MIT (https://huggingface.co/ResembleAI/chatterbox). Both allow commercial use.

## Whose voice

- Default: the built-in voice. No recording, no consent step.
- The founder's own voice: only from a recording of the founder's own voice that the founder gives for this purpose. Ask first, in words: "Do you want the narration in your own voice? If yes, send a clean 10 to 20 second recording of you speaking, and confirm it is your voice and that you agree to it being cloned for this video." Go on only after a clear yes and their file.
- Never clone another person's voice, a celebrity's, a generated presenter's or a voice from a found clip, whatever the reason. No AI people in Onca videos, and that includes their voices.

## Make a line

```bash
python3 scripts/say.py --text "Your whole clipboard, kept." --out voice-out --prefix line1
python3 scripts/say.py --text "..." --out voice-out --prefix line1 --ref founder-voice.wav   # the founder's own voice
```

- Write product names as they are said, in a phonetic spelling (for example `Acme` as `Ak-mee`), and read the output names back to check.
- `--exaggeration 0.5` is the start value; raise it toward 0.7 for more energy, lower it toward 0.3 for calm. Keep 0 to 1.
- One WAV per call (`voice-out/<prefix>.wav`). Make one line per scene, so each can be timed to its scene.
- Listen is the founder's: you cannot hear the audio. Give them the files, ask them to listen, and fix the lines they flag.

## Into the video

- Place each line in the composition at its scene (the `hyperframes` skill's sound reference shows how), or mix with ffmpeg.
- The finished video goes through the video-render skill's finish step, which sets loudness to -16 LUFS.
