# Connect Escalate Anything to your AI apps

Escalate Anything is a standard [MCP](https://modelcontextprotocol.io) server. Any app that speaks MCP can use it.

**Fastest:** let Escalate Anything find your apps and add itself:

```bash
uvx escalate-anything --help          # check that uv can run it
uvx escalate-anything install --list
uvx escalate-anything install --all
```

`escalate install` merges into each app's config file, backs the file up first (`*.bak-escalate-<time>`), and never rewrites files that can hold comments or YAML. For those, it prints the snippet to paste. `escalate uninstall <app>` removes it again. Add `--dry-run` to preview.

Every app below runs the same command: `uvx escalate-anything`. Until the first PyPI release, use `uvx --from git+https://github.com/alexgaoth/escalate-anything escalate-anything` instead.

## One-click

| App | Install |
|---|---|
| Cursor | [![Install in Cursor](https://cursor.com/deeplink/mcp-install-dark.svg)](https://cursor.com/install-mcp?name=escalate-anything&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyJlc2NhbGF0ZS1hbnl0aGluZyJdfQ%3D%3D) |
| VS Code | [![Install in VS Code](https://img.shields.io/badge/VS_Code-Install_Server-0098FF?style=flat-square&logo=visualstudiocode&logoColor=white)](https://insiders.vscode.dev/redirect/mcp/install?name=escalate-anything&config=%7B%22type%22%3A%22stdio%22%2C%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22escalate-anything%22%5D%7D) [![Install in VS Code Insiders](https://img.shields.io/badge/VS_Code_Insiders-Install_Server-24bfa5?style=flat-square&logo=visualstudiocode&logoColor=white)](https://insiders.vscode.dev/redirect/mcp/install?name=escalate-anything&quality=insiders&config=%7B%22type%22%3A%22stdio%22%2C%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22escalate-anything%22%5D%7D) |
| LM Studio | [![Add to LM Studio](https://files.lmstudio.ai/deeplink/mcp-install-dark.svg)](https://lmstudio.ai/install-mcp?name=escalate-anything&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyJlc2NhbGF0ZS1hbnl0aGluZyJdfQ%3D%3D) |
| Goose | [![Install in Goose](https://block.github.io/goose/img/extension-install-dark.svg)](https://block.github.io/goose/extension?cmd=uvx&arg=escalate-anything&id=escalate-anything&name=escalate-anything&description=Contacts%2C+playbooks+and+escalation+paths+to+get+US+companies+to+fix+problems) |

## By app

| App | Command or file | Notes |
|---|---|---|
| **Claude Code** | `claude mcp add --scope user escalate-anything -- uvx escalate-anything`, or the plugin: `claude plugin marketplace add alexgaoth/escalate-anything` then `claude plugin install escalate-anything@escalate-anything` | The plugin also adds the 5 skills. |
| **Claude Desktop** | `escalate install claude-desktop`, or add to `claude_desktop_config.json` (macOS: `~/Library/Application Support/Claude/`, Windows: `%APPDATA%\Claude\`) | Quit the app completely and reopen. The workflows appear as prompts. |
| **Cursor** | `~/.cursor/mcp.json` → `mcpServers` | One-click link above. |
| **VS Code** (Copilot agent mode) | `code --add-mcp '{"name":"escalate-anything","command":"uvx","args":["escalate-anything"]}'` or user `mcp.json` → `servers` | Note the key is `servers`, not `mcpServers`. |
| **Windsurf / Devin Desktop** | `~/.config/devin/mcp_config.json` (older: `~/.codeium/windsurf/mcp_config.json`) → `mcpServers` | Windsurf was renamed Devin Desktop in 2026. |
| **Cline** | `~/.cline/data/settings/cline_mcp_settings.json` → `mcpServers` with `"type": "stdio"` | Cline moved this file in 2026. |
| **Zed** | `~/.config/zed/settings.json` → `context_servers` | The file can hold comments; `escalate install zed` prints the snippet if it does. |
| **Gemini CLI** | `gemini mcp add -s user escalate-anything uvx escalate-anything` | Without `-s user`, the server is added to the current project only. |
| **OpenAI Codex** (CLI, IDE, desktop app) | `codex mcp add escalate-anything -- uvx escalate-anything`, or `~/.codex/config.toml` → `[mcp_servers.escalate-anything]` | |
| **Goose** | `goose session --with-extension "uvx escalate-anything"`, or the one-click link | |
| **LM Studio** | `~/.lmstudio/mcp.json` → `mcpServers` | Reloads on save. |
| **Continue** | `~/.continue/config.yaml` → `mcpServers:` list item with `type: stdio` | |
| **JetBrains** | Junie: `~/.junie/mcp/mcp.json`. AI Assistant: Settings → Tools → AI Assistant → Model Context Protocol | |

## Remote-only apps: ChatGPT, claude.ai web and mobile

These apps connect only to an HTTPS URL, not to a program on your computer. Run the **read-only** server somewhere public:

```bash
docker build -t escalate-anything . && docker run -p 8765:8765 escalate-anything      # serves http://localhost:8765/mcp
```

Then put HTTPS in front of it (a host such as Render with the included `render.yaml`, or a tunnel), and add `https://<your-host>/mcp`:
- **claude.ai:** Customize → Connectors → Add custom connector.
- **ChatGPT:** Settings → Connectors (developer mode) → add a custom MCP server. Full MCP support depends on the plan.

The read-only server has every lookup, `get_context` and `scam_check`. It has no case log, because a shared server must not hold anyone's case history.

## No MCP at all

Agents that can fetch URLs, such as browser agents, can read the static site:
- `https://intro.alexgaoth.com/escalate-anything/registry.json`: everything
- `https://intro.alexgaoth.com/escalate-anything/companies/<id>.json`: one company with its playbooks
- `https://intro.alexgaoth.com/escalate-anything/llms.txt`: an index for language models

People can use the CLI:

```bash
uvx escalate-anything playbook xfinity bill_increase --state CA
uvx escalate-anything lookup chase
```

Paths and formats were checked against each app's documentation on 2026-10-12. Apps change these often; please open an issue if one is out of date.
