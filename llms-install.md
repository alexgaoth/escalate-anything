# Installing Escalate Anything (for AI agents)

Escalate Anything is a local MCP server (stdio). It needs no API key and no account.

1. Make sure `uv` is installed: run `uv --version`. If it is missing, install it from https://docs.astral.sh/uv/getting-started/installation/ (macOS/Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`).
2. Add this server to the MCP settings file:

```json
{
  "mcpServers": {
    "escalate-anything": {
      "command": "uvx",
      "args": ["escalate-anything"]
    }
  }
}
```

3. Restart or reload the MCP servers. The server exposes 19 tools; start with `find_company`, then `get_playbook`.
4. Check it works: call `find_company` with `{"query": "united"}`. The result should include `united-airlines`.

Optional: `uvx escalate-anything setup` configures Claude Desktop, Claude Code, Cursor, VS Code, Windsurf, Zed, Gemini CLI, Codex, LM Studio and others in one step. It shows the changes and asks before it writes.

Data: the server reads a bundled registry and updates it weekly from GitHub. The case log stays in `~/.escalate-anything` on the user's computer.
