# redress

An open index of how to get problems resolved with large US companies, plus an MCP server and agent skills that use it.

Agents that complain, dispute or negotiate for a person usually fail in the same places. They search the web for the right form, land on a page that needs a sign-in, cite a rule that was vacated, and lose track of what the company promised. redress gives them:

- **A registry** (`registry/`): for each company, its contact channels with deep links, its playbooks per issue, its escalation ladder and its known blockers. It also has federal regulators, state agencies for all 50 states and DC, and consumer-protection rules with their current status. Every value has a source URL and a `last_verified` date.
- **An MCP server** (`redress serve`): lookups over the registry, a local case log (timeline, reference numbers, promises, follow-ups), draft briefs with citable facts and tone rules, and bill tracking that flags increases and ending promotions.
- **Skills** (`skills/`): `resolve`, `negotiate-bill`, `regulator-complaint` and `bill-watch`.

Agents draft. The person approves every message and form submission.

## Install

Requires [uv](https://docs.astral.sh/uv/).

Claude Code, as a plugin (MCP server and skills):

```bash
claude plugin marketplace add /path/to/redress --scope user
claude plugin install redress@redress-local --scope user
```

Claude Desktop (chat), MCP server only: add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{ "mcpServers": { "redress": { "command": "/opt/homebrew/bin/uv",
  "args": ["run", "--quiet", "--directory", "/path/to/redress", "redress", "serve"] } } }
```

Other agents: `redress serve --transport http --port 8765` serves MCP over streamable HTTP. Agents without MCP support can read `redress export -o dist/registry.json`.

## Use

Ask the agent, for example:

- "United lost my bag on Friday's ORD–SFO flight. Get me reimbursed."
- "My Xfinity bill went from $80 to $105. Get it back down."
- "Check my bills for increases."
- "AT&T never credited my returned router. Escalate."

## Commands

| Command | What it does |
|---|---|
| `uv run redress validate [files]` | Check registry files against the schema and cross references |
| `uv run redress stats` | Count companies, playbooks, regulators and rules |
| `uv run redress stale --days 180` | List values not verified recently |
| `uv run redress check-links` | Check that every registry URL still answers |
| `uv run redress cases [id]` | Show the local case log |
| `uv run redress feedback` | Show registry problems that agents reported |
| `uv run redress export` | Write the registry as one JSON file |

The case log is stored locally in `~/.redress/redress.db` (set `REDRESS_HOME` to move it). It refuses full card numbers and SSNs.

## Contributing data

See [docs/authoring.md](docs/authoring.md). Never guess a value. A missing entry is safe; a wrong one sends an agent to the wrong place.

## Limits

- This is not legal advice. Rules carry a status and a source; check the source before relying on a rule.
- Contacts change. The weekly `freshness` workflow checks links. Many company sites block automated checks, so those links are reported as "blocked", not dead.
- Phone calls are not automated. The skills prepare a script for the person.
