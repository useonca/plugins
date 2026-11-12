# Providers: who does each step

Every step uses the free local tool unless `providers.json` says otherwise. Pass the file with `--providers` to `transcribe.py`, `audio.py separate` and `cut.py`.

```json
{"transcribe": {"kind": "command", "argv": ["my-asr", "{in}", "--json", "{out}"]},
 "separate": {"kind": "file", "path": "stems/"},
 "encode": {"kind": "local", "name": "x264"}}
```

| Step | Local default | Result format |
|---|---|---|
| `transcribe` | the speech recognizer `doctor.py` checks | words (parakeet or whisper JSON works too) |
| `voice` | the `voice` skill's `say.py` | a WAV, used as a timeline source |
| `separate` | the voice separator `doctor.py` lists as optional | a folder with `vocals.wav` and `background.wav` |
| `encode` | the hardware encoder, else software (`name`: `auto`, `videotoolbox`, `nvenc`, `qsv`, `amf`, `x264`, `x264-fast`) | the render itself |

## Kinds

- `local`: the built-in tool.
- `command`: another free program on this computer. `argv` is the command as a list (no shell), with `{in}` (the input file), `{out}` (the file to write) and `{out_dir}` (a folder to write into). It must exit 0 and write its result in the step's format; anything else stops the step with exit 1, naming the provider and the reason, and nothing is written.
- `file`: a result the client already has, for example from an Onca service reached through Onca's tools (which ask the founder and keep to the spend caps). `path` is the file or folder.

Narration from Onca voice (the `voice` skill, paid in Onca credits after the founder's yes) needs no provider entry: `make_voiceover`'s `download` line saves each line as `voice/{line id}.wav`, and each file goes into the timeline like any sound (`references/timeline.md`): a `sources` name (`"vo_hook": "voice/hook.wav"`) and an `audio` entry at its scene (`{"src": "vo_hook", "in": 0, "out": 3.2, "at": 0}`, `out` from the line's `duration_ms`).

There is no network kind: these scripts hold no keys and never pay for anything. A `command` whose program is a known paid CLI is refused.

## Words

A words file is any of: the recognizer's own JSON, a list of words, or `{"words": [...]}`, where each word has `text` (or `word`) and `start` / `end` in seconds (or `start_ms` / `end_ms`). It is read into `[{"i", "text", "start", "end"}]` sorted by start.
