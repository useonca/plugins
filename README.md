# Onca plugins

The Onca plugin for Claude Code, Codex and Claude Desktop, from Onca (https://useonca.com), the launch hub for solo founders. It carries Onca's hosted MCP (one install) and the video skills, which run on the founder's own Mac; Onca tells the client which version is current. In Claude Code the plugin's MCP declaration sends the header `X-Onca-Plugin: <plugin version>` (its own public version number, nothing else), so Onca can tell a client that has the plugin from one that does not and offer the install.

| Plugin | What it does |
|--------|--------------|
| `onca` | Onca's launch tools (the hosted MCP) and free launch videos from your product's real UI: the Onca method, local rendering, a video editor and local narration. |

Install in Claude Code: `claude plugin marketplace add useonca/plugins`, then `claude plugin install onca@onca`.
Install in Codex: `codex plugin marketplace add useonca/plugins`, then `codex plugin add onca@onca`.
In Claude Desktop: Customize, Plugins, add the marketplace `useonca/plugins`, Discover, Install, then connect Onca in the plugin's Connectors tab.

Each plugin carries its own LICENSE and NOTICE.
