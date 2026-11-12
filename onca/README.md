# Onca

One install for your AI client (Claude Code, Codex or Claude Desktop). It connects the client to Onca, your all-in-one online presence platform, and teaches it to make short videos for your product on your Mac or Windows PC, for free. The video skills teach the client Onca's video method: a hook, the value shown in your product's real UI, and a closure that pays the hook off; five very different concepts to pick from; parallel builds; a self-review before you watch. It renders HTML to 9:16 video locally, edits screen recordings into captioned shorts, and narrates with a free local voice. Nothing is uploaded or paid for unless you say yes to a specific run.

## Skills

- `launch-video`: the method, from facts to the posted video (start here).
- `video-render`: the render contract and the local, pinned render engine.
- `video-edit`: Onca's local editor: map a raw recording, cut it fast, clean the voice, and lay in cutaways, picture-in-picture, music and captions from one timeline.
- `voice`: free local narration (an M-series Mac, or Windows through Kokoro).
- `screen-demo` (Onca production kit): product footage made from your product's own source or a headless recording, polished with auto zoom and a smooth cursor, and long chaptered YouTube demos with captions. You never record or stage anything.
- `b-roll` (Onca production kit): moving shots from still photos (Onca's parallax or a pan and zoom) and code-made depth scenes, and where to cut them in.
- `hyperframes`, `hyperframes-cli`: the render engine's own skills (HyperFrames, Apache 2.0, see NOTICE).

## Install

If an Onca server is already signed in (the plugin's onca or the claude.ai connector claude_ai_onca), use it and do not sign in again.

Claude Code:

```bash
claude plugin marketplace add useonca/plugins
claude plugin install onca@onca
```

Then run `/reload-plugins`, then `/mcp`, choose onca and Authenticate.

Codex:

```bash
codex plugin marketplace add useonca/plugins
codex plugin add onca@onca
```

Then start a new Codex session and sign in to Onca when it asks.

Claude Desktop: Customize, Plugins, add the marketplace `useonca/plugins`, Discover, Install, then open the plugin's Connectors tab and connect Onca.

The plugin declares Onca's hosted MCP in `.mcp.json` (Claude Code) and `mcp.json` (Codex), so nothing else needs installing. Onca tells your client when a newer version is out and how to update. The video skills need Node 22+, ffmpeg and uv on the Mac or Windows PC; `python3 skills/video-render/scripts/doctor.py check` (Windows: `py -3 -X utf8 skills\video-render\scripts\doctor.py check`) lists what is missing, with the install command for each.

## Licence

See LICENSE and NOTICE.
