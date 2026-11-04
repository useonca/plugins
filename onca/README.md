# Onca

One install for your AI client (Claude Code, Codex or Claude Desktop). It connects the client to Onca, your launch hub, and teaches it to make launch videos for your product on your own Mac, for free. The video skills teach the client Onca's video method: a hook, the value shown in your product's real UI, and a closure that pays the hook off; five very different concepts to pick from; parallel builds; a self-review before you watch. It renders HTML to 9:16 video locally, edits screen recordings into captioned shorts, and narrates with a free local voice. Nothing is uploaded or paid for unless you say yes to a specific run.

## Skills

- `launch-video`: the method, from facts to the posted video (start here).
- `video-render`: the render contract and the local, pinned render engine.
- `video-edit`: cut a raw recording into a tight captioned short.
- `voice`: free local narration (Apple Silicon).
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

The plugin declares Onca's hosted MCP in `.mcp.json` (Claude Code) and `mcp.json` (Codex), so nothing else needs installing. Onca tells your client when a newer version is out and how to update. The video skills need Node 22+, ffmpeg and uv on the Mac; `python3 skills/video-render/scripts/doctor.py check` lists what is missing.

## Licence

See LICENSE and NOTICE.
