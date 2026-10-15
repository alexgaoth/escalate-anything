"""Turn a case from the local log into a short write-up that a person can post or share.

Reference numbers, representative names and account hints are left out, and long digit runs in
free text are masked. The person still reads it before posting: summaries and notes are their words.
"""

from __future__ import annotations

import datetime as dt
import re

from .advisor import NotFound, resolve_company
from .registry import Registry
from .site import BASE_URL

REPO_URL = "https://github.com/alexgaoth/escalate-anything"
_DIGITS_RE = re.compile(r"\b[A-Z]{0,4}\d[\dA-Z-]{5,}\b")


def _mask(text: str | None) -> str:
    """Hide reference-like tokens (6+ characters with digits) that people paste into notes."""
    return _DIGITS_RE.sub("[ref]", text or "").strip()


def _day(value: str | None) -> dt.date | None:
    return dt.date.fromisoformat(value[:10]) if value else None


def _company(reg: Registry, name: str) -> dict | None:
    try:
        return resolve_company(reg, name)
    except NotFound:
        return None


def playbook_url(company: str, issue: str, reg: Registry) -> str:
    known = _company(reg, company)
    if known:
        return f"{BASE_URL}c/{known['id']}/{issue.replace('_', '-')}/"
    return BASE_URL


def case_story(case: dict, reg: Registry) -> str:
    """Markdown for one case, as returned by Store.get_case."""
    known = _company(reg, case["company"])
    company = known["name"] if known else case["company"]
    issue = reg.issues.get(case["issue"], {}).get("name", case["issue"].replace("_", " "))
    outcome = case.get("outcome") or "still open"
    amount = case.get("amount_recovered")
    # Events can be logged with earlier dates than the day the case was opened in the log.
    event_days = [_day(e["occurred_on"]) for e in case.get("events") or [] if e.get("occurred_on")]
    opened = min([d for d in [_day(case.get("opened_at")), *event_days] if d], default=None)
    closed = _day(case.get("closed_at"))

    headline = f"{company}: {issue}"
    if amount:
        headline += f" → ${amount:,.2f} back"
    elif case.get("outcome"):
        headline += f" → {outcome}"
    lines = [f"# {headline}", ""]
    facts = [f"- Outcome: {outcome}" + (f", ${amount:,.2f} recovered" if amount else "")]
    if opened and closed:
        facts.append(f"- Time: {(closed - opened).days} days ({opened.isoformat()} to {closed.isoformat()})")
    elif opened:
        facts.append(f"- Opened: {opened.isoformat()}")
    if case.get("what_worked"):
        facts.append(f"- What worked: {_mask(case['what_worked'])}")
    if case.get("rungs_used"):
        facts.append(f"- Escalation steps used: {', '.join(r.replace('_', ' ') for r in case['rungs_used'])}")
    facts.append(f"- Playbook: {playbook_url(case['company'], case['issue'], reg)}")
    lines += facts + ["", "## What happened", "", _mask(case.get("summary")), ""]

    events = case.get("events") or []
    if events:
        lines += ["## Timeline", ""]
        for e in events:
            where = " · ".join(x.replace("_", " ") for x in (e.get("kind"), e.get("rung"), e.get("channel")) if x)
            lines.append(f"- {e['occurred_on']} · {where}: {_mask(e.get('text'))}")
        lines.append("")
    lines += [
        "_Reference numbers, names and account details are left out. Read it before you post it._",
        "",
        f"Made with Escalate Anything, free and open source: {REPO_URL}",
    ]
    return "\n".join(lines) + "\n"
