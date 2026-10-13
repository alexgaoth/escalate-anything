# Writing dossiers, guides and security data

Playbooks say *what to do*. Dossiers and guides say *how it actually goes*: how a company handles complaints, which channel gets results, and what traps to avoid. A smaller section covers the scams that use each company's name.

Validate everything with `uv run escalate validate <files>`.

## 1. Company security data (in `registry/companies/<sector>/<id>.yaml`)

```yaml
official_domains: [xfinity.com, comcast.com, comcast.net]   # domains the company uses for web and email

security:
  never_asks:          # what the company says it will never ask for, from its own security page
    - kind: policy
      claim: Xfinity will never ask for your password or full card number in an unsolicited call, text or email.
      source: https://www.xfinity.com/support/articles/...
      last_verified: 2026-10-12
  known_scams:         # scams that impersonate this company, from the company, the FTC, the FCC, the BBB or a state AG
    - kind: policy
      claim: Scammers call claiming to offer a discount if you prepay several months with gift cards.
      source: https://...
      last_verified: 2026-10-12
  report_phishing:     # where to report impersonation (channel objects, as in `channels`)
    - id: phishing-email
      type: email
      label: Report phishing emails
      value: abuse@example.com
      source: https://...
      last_verified: 2026-10-12
```

Rules: `official_domains` must include the domain of `website`. List only domains the company itself uses (from its security page, or from where its own help and email live). Never add look-alike domains.

## 2. Company dossiers (`registry/dossiers/<company-id>.md`)

```markdown
---
company: comcast-xfinity
title: Xfinity — how complaints actually go
last_verified: 2026-10-12
---

## In short

Two to four plain sentences: the fastest route to a fix and the main thing to avoid. No links needed here.

## How complaints actually go

- Tiers, what each tier can do, typical response times, where escalations land. [Source](https://...)

## What tends to work

- Specific tactics with a source. [Source](https://...)
- Reported by customers: an anecdotal tactic from a forum. [Reddit thread](https://reddit.com/...)

## Traps and fine print

- Retention offers that restart a contract, fees, deadlines that waive rights, arbitration clauses. [Source](https://...)

## By the numbers

- Complaint counts or rankings from DOT, CFPB, FCC, J.D. Power, ACSI or state data, with the period. [Source](https://...)

## Scams that target customers

- Impersonation patterns, with the official way to verify. [Source](https://...)
```

## 3. Sector guides (`registry/guides/<sector-id>.md`) and the scam guide (`registry/guides/scams.md`)

Front matter: `sector: <sector-id>` (or `topic: scams`), `title`, `last_verified`. Sector guide sections: `In short`, `How complaints work in this industry`, `Your leverage`, `Traps`, `Scams to watch for`, optional `By the numbers`. The scam guide has free sections, but the same bullet and citation rules apply.

## Rules the validator enforces

- Every line outside `In short` is a bullet (`- `) with at least one source link `[text](https://...)`.
- At least 3 distinct sources per file.
- A forum source (Reddit, FlyerTalk, DSLReports, Quora, TripAdvisor, Facebook, X) needs the words `Reported by customers` in the bullet, so agents know it is an anecdote.

## Rules the validator cannot enforce

- **Sources first**: the company's own pages, regulators (DOT Air Travel Consumer Report, CFPB complaint database, FCC data, state AGs), court and enforcement records (FTC, CFPB, state AG actions), reputable news, Consumer Reports. Forums only for tactics, and marked.
- **No guessing.** Quote numbers exactly, with their period ("Q2 2026", "2025 calendar year").
- **Neutral tone.** Describe what happens and what works. No editorializing, no "this company is a scam".
- **Current.** Note when something changed (mergers, new policies, rules vacated).
