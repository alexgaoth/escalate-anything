# Contributing to redress

Thank you. Every correct phone number, form link or deadline saves someone an afternoon on hold, and every flagged fake number can save someone real money.

## The fastest way to help: report a wrong value

[Open a data correction](https://github.com/alexgaoth/redress/issues/new?template=data-correction.yml). Tell us the company, what is wrong, and the official page that shows the right value. That is all we need.

## Share what worked

Got a refund, a credit or a fix? [Share your case](https://github.com/alexgaoth/redress/issues/new?template=share-your-case.yml): the company, the problem, the channel or argument that worked, and how long it took. Good cases become "Reported by customers" tactics in the company's dossier, linked to your issue.

## Edit the data yourself

The registry is plain YAML and Markdown in [`registry/`](registry):

| What | Where | Guide |
|---|---|---|
| Company contacts, playbooks, facts | `registry/companies/<sector>/<id>.yaml` | [docs/authoring.md](docs/authoring.md) |
| How a company handles complaints, scams | `registry/dossiers/<id>.md`, `security:` in the company file | [docs/context.md](docs/context.md) |
| Industry guides, scam guide | `registry/guides/` | [docs/context.md](docs/context.md) |
| Regulators, state agencies, rules | `registry/regulators/`, `registry/states/`, `registry/rules/` | [docs/authoring.md](docs/authoring.md) |

```bash
git clone https://github.com/alexgaoth/redress && cd redress
uv sync
uv run redress validate registry/companies/airline/united-airlines.yaml
uv run pytest -q
```

### How your change is checked

- `redress validate` checks the schema, cross-references, formats, dates and dossier citations.
- `redress credibility <company>` shows the company's grade, how many sources are official, and the verification dates. Aim for grade A.
- Set `verified_via` when you did not read the live page: `search_snippet`, `archive` or `document`. Those values count against the grade until someone re-checks them.
- See [docs/maintenance.md](docs/maintenance.md) for the weekly report and the routines that keep the data fresh.

### The rules that keep the data trustworthy

1. **Every value has a `source` and a `last_verified` date.** Prefer the company's or the government's own page.
2. **Never guess.** A missing value is safe; a wrong one sends someone to the wrong place, or to a scammer.
3. **Official contacts only.** Never add a number or link from a search ad, a forum post or a third-party "contact directory".
4. **Mark anecdotes.** Tactics from forums go in dossiers as "Reported by customers:" bullets, with the link.
5. **Neutral tone.** Describe what happens and what works. No accusations.

## Code

The MCP server, CLI and website live in `src/redress/`. Run `uv run pytest -q` before opening a PR; CI runs the same checks plus a clean-install test of the wheel.

## Something unsafe?

If you find a value in redress that points to a scam, open an issue titled **"Unsafe contact"**. We treat these first.
