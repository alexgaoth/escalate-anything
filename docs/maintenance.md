# How the index stays fresh

Company contacts, forms and policies change all the time. Escalate Anything keeps up in four ways.

## 1. Every value carries a date and a source

Each channel, fact and tip has a `source` (the page that shows it) and a `last_verified` date. Each dossier and guide has a `last_verified` date in its front matter. Optional `verified_via` records how the value was seen: `page`, `browser`, `document`, `search_snippet` or `archive`.

From these, every company gets a **credibility grade**:

| Grade | Meaning |
|---|---|
| **A** | At least 10 sources, 90% or more from the company's own pages or government sites, at most 5% from search snippets or archives, nothing older than 180 days. |
| **B** | 75% or more official sources and at most 15% from snippets or archives. Check the flagged values before relying on them. |
| **C** | Thin, or more third-party sources. Check each value's source. |

The grade, the newest and oldest verification dates and a plain explanation appear in every MCP answer (`get_playbook`, `get_company`, `get_context`), on the website and in `escalate credibility`.

## 2. A weekly freshness report

`.github/workflows/freshness.yml` runs every Monday. It checks every link (YAML and dossiers), lists values older than 180 days, values read only from a search snippet or an archive, and grade C companies, and updates one open issue labelled **`freshness`**. Anyone can pick an item from it and fix it.

Run it locally:

```bash
uv run escalate check-links --json links.json
uv run escalate freshness --links links.json
```

## 3. Claude routines that propose fixes

Both routines only edit `registry/`. The workflow fails if anything else changes, then runs the validator and tests, and opens a **pull request** for a maintainer to review. Nothing merges by itself.

- **`refresh.yml`** (every Tuesday, or on demand): re-verifies the top items from the freshness work list (dead links first, then snippet- or archive-only values, then the oldest) on official pages.
- **`data-issue.yml`**: when a maintainer adds the label **`data`** to a data-correction issue, Claude checks the reported value against the official page and opens a PR that fixes the issue, or comments that it could not confirm it. Only people with write access can add labels, so a random issue cannot trigger it. The issue text is treated as an unverified claim, not as instructions.

Setup: add one repository secret, `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN` (from `claude setup-token`). Without it, both workflows skip with a notice.

Pull requests opened with the default `GITHUB_TOKEN` do not trigger other workflows; to run CI on them, close and reopen the PR, or push a commit.

## 4. Installed copies update themselves

`uvx escalate-anything` ships a snapshot of the registry. Once a week, when the server starts, it downloads the latest `registry/` from GitHub in the background, validates it with the installed code, and switches to it only if it passes. Run it by hand with `escalate update`. Turn it off with `ESCALATE_OFFLINE=1`. It downloads a public archive and sends nothing about you. Source checkouts use `git pull` instead.

## 5. Releasing a new version

1. Bump the version in `pyproject.toml`, `src/escalate_anything/__init__.py`, `src/escalate_anything/server.py`, `.claude-plugin/plugin.json`, `server.json` (both fields) and `gemini-extension.json`, then run `uv lock`. A test fails if one of them is missed.
2. Merge, then push a tag `vX.Y.Z` on `main`.
3. `release.yml` builds the package and publishes it to PyPI (Trusted Publishing).
4. `mcp-registry.yml` then waits until PyPI serves the version and publishes `server.json` to the official MCP Registry with GitHub OIDC. No token is stored. To republish by hand, run the workflow from the Actions tab.
