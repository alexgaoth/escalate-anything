"""Local case log, bill history and registry feedback, in SQLite.

The database stays on this machine (default ~/.redress/redress.db).
It refuses text that looks like a full card number or SSN.
"""

from __future__ import annotations

import datetime as dt
import os
import re
import sqlite3
import statistics
import threading
from functools import wraps
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  company TEXT NOT NULL,
  issue TEXT NOT NULL,
  state TEXT,
  summary TEXT NOT NULL,
  desired_outcome TEXT,
  amount REAL,
  account_hint TEXT,
  status TEXT NOT NULL DEFAULT 'open',
  outcome TEXT,
  amount_recovered REAL,
  what_worked TEXT,
  opened_at TEXT NOT NULL,
  closed_at TEXT
);
CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  case_id INTEGER NOT NULL REFERENCES cases(id),
  occurred_on TEXT NOT NULL,
  kind TEXT NOT NULL,
  text TEXT NOT NULL,
  rung TEXT,
  channel TEXT,
  reference TEXT,
  rep_name TEXT,
  promised TEXT,
  follow_up_on TEXT,
  logged_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bills(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  company TEXT NOT NULL,
  period_end TEXT NOT NULL,
  amount REAL NOT NULL,
  plan TEXT,
  promo_end TEXT,
  note TEXT,
  recorded_at TEXT NOT NULL,
  UNIQUE(company, period_end)
);
CREATE TABLE IF NOT EXISTS feedback(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entity TEXT NOT NULL,
  location TEXT,
  problem TEXT NOT NULL,
  reported_at TEXT NOT NULL
);
"""

EVENT_KINDS = {"contact", "sent", "response", "promise", "reference", "document", "escalation", "note"}
OUTCOMES = {"resolved", "partial", "failed", "abandoned"}
RUNGS = {"frontline", "supervisor", "retention", "written_complaint", "executive", "regulator", "state_agency", "payment_dispute", "arbitration", "small_claims", "public"}

_CARD_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")


class StoreError(ValueError):
    pass


def default_path() -> Path:
    home = Path(os.environ.get("REDRESS_HOME", Path.home() / ".redress"))
    return home / "redress.db"


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def _luhn(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2:
            n = n * 2 - 9 if n > 4 else n * 2
        total += n
    return total % 10 == 0


def _check_sensitive(*values: Any, cards: bool = True) -> None:
    for v in values:
        if not isinstance(v, str):
            continue
        if _SSN_RE.search(v):
            raise StoreError("This text looks like an SSN. Do not store it.")
        if cards:
            for m in _CARD_RE.finditer(v):
                if _luhn(re.sub(r"\D", "", m.group())):
                    raise StoreError("This text looks like a full card number. Store only the last 4 digits.")


def _date(value: str | None, field: str) -> str | None:
    if value in (None, ""):
        return None
    try:
        return dt.date.fromisoformat(value).isoformat()
    except ValueError as e:
        raise StoreError(f"{field} must be YYYY-MM-DD, got '{value}'") from e


def _locked(fn):
    """MCP runs sync tools in worker threads; serialize access to the one connection."""
    @wraps(fn)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return fn(self, *args, **kwargs)
    return wrapper


class Store:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else default_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    # ---- cases -------------------------------------------------------------

    @_locked
    def open_case(self, company: str, issue: str, summary: str, desired_outcome: str | None = None,
                  amount: float | None = None, state: str | None = None, account_hint: str | None = None) -> dict:
        _check_sensitive(summary, desired_outcome, account_hint)
        if account_hint and len(re.sub(r"\D", "", account_hint)) > 4:
            raise StoreError("account_hint must be at most the last 4 digits.")
        cur = self.db.execute(
            "INSERT INTO cases(company, issue, state, summary, desired_outcome, amount, account_hint, opened_at) VALUES(?,?,?,?,?,?,?,?)",
            (company, issue, state.lower() if state else None, summary, desired_outcome, amount, account_hint, _now()),
        )
        self.db.commit()
        return self.get_case(cur.lastrowid)

    @_locked
    def log_event(self, case_id: int, kind: str, text: str, occurred_on: str | None = None, rung: str | None = None,
                  channel: str | None = None, reference: str | None = None, rep_name: str | None = None,
                  promised: str | None = None, follow_up_on: str | None = None) -> dict:
        if kind not in EVENT_KINDS:
            raise StoreError(f"kind must be one of {sorted(EVENT_KINDS)}")
        if rung and rung not in RUNGS:
            raise StoreError(f"rung must be one of {sorted(RUNGS)}")
        _check_sensitive(text, promised)
        _check_sensitive(reference, cards=False)  # tracking and confirmation numbers are long digit strings
        case = self._case_row(case_id)
        if case["status"] != "open":
            raise StoreError(f"case {case_id} is closed")
        self.db.execute(
            "INSERT INTO events(case_id, occurred_on, kind, text, rung, channel, reference, rep_name, promised, follow_up_on, logged_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (case_id, _date(occurred_on, "occurred_on") or dt.date.today().isoformat(), kind, text, rung, channel,
             reference, rep_name, promised, _date(follow_up_on, "follow_up_on"), _now()),
        )
        self.db.commit()
        return self.get_case(case_id)

    @_locked
    def close_case(self, case_id: int, outcome: str, amount_recovered: float | None = None,
                   what_worked: str | None = None) -> dict:
        if outcome not in OUTCOMES:
            raise StoreError(f"outcome must be one of {sorted(OUTCOMES)}")
        _check_sensitive(what_worked)
        self._case_row(case_id)
        self.db.execute(
            "UPDATE cases SET status='closed', outcome=?, amount_recovered=?, what_worked=?, closed_at=? WHERE id=?",
            (outcome, amount_recovered, what_worked, _now(), case_id),
        )
        self.db.commit()
        return self.get_case(case_id)

    def _case_row(self, case_id: int) -> sqlite3.Row:
        row = self.db.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
        if not row:
            raise StoreError(f"no case {case_id}")
        return row

    @_locked
    def get_case(self, case_id: int) -> dict:
        case = dict(self._case_row(case_id))
        events = [dict(r) for r in self.db.execute("SELECT * FROM events WHERE case_id=? ORDER BY occurred_on, id", (case_id,))]
        case["events"] = events
        case["rungs_used"] = sorted({e["rung"] for e in events if e["rung"]})
        case["promises"] = [{"on": e["occurred_on"], "by": e["rep_name"], "promised": e["promised"]} for e in events if e["promised"]]
        case["references"] = [{"on": e["occurred_on"], "reference": e["reference"], "channel": e["channel"]} for e in events if e["reference"]]
        case["follow_up"] = self._pending_follow_up(events)
        return case

    @staticmethod
    def _pending_follow_up(events: list[dict]) -> dict | None:
        """The latest reminder, unless something was logged after it."""
        reminders = [e for e in events if e["follow_up_on"]]
        if not reminders:
            return None
        e = max(reminders, key=lambda r: r["id"])
        if any(other["id"] > e["id"] for other in events):
            return None
        return {"on": e["follow_up_on"], "after_event": e["id"], "about": e["text"]}

    @_locked
    def list_cases(self, status: str | None = "open") -> list[dict]:
        if status:
            rows = self.db.execute("SELECT id FROM cases WHERE status=? ORDER BY id", (status,))
        else:
            rows = self.db.execute("SELECT id FROM cases ORDER BY id")
        out = []
        for (cid,) in rows.fetchall():
            c = self.get_case(cid)
            out.append({k: c[k] for k in ("id", "company", "issue", "status", "summary", "opened_at", "outcome", "follow_up")} | {"events": len(c["events"])})
        return out

    @_locked
    def followups_due(self, on_or_before: str | None = None) -> list[dict]:
        limit = _date(on_or_before, "on_or_before") or dt.date.today().isoformat()
        due = []
        for c in self.list_cases("open"):
            fu = c["follow_up"]
            if fu and fu["on"] <= limit:
                due.append({"case_id": c["id"], "company": c["company"], "issue": c["issue"], "follow_up": fu})
        return due

    @_locked
    def outcome_stats(self, company: str | None = None) -> list[dict]:
        sql = ("SELECT company, issue, outcome, COUNT(*) n, SUM(amount_recovered) recovered FROM cases"
               " WHERE status='closed'" + (" AND company=?" if company else "") + " GROUP BY company, issue, outcome")
        return [dict(r) for r in self.db.execute(sql, (company,) if company else ())]

    # ---- bills -------------------------------------------------------------

    @_locked
    def record_bill(self, company: str, period_end: str, amount: float, plan: str | None = None,
                    promo_end: str | None = None, note: str | None = None) -> dict:
        _check_sensitive(plan, note)
        self.db.execute(
            "INSERT INTO bills(company, period_end, amount, plan, promo_end, note, recorded_at) VALUES(?,?,?,?,?,?,?)"
            " ON CONFLICT(company, period_end) DO UPDATE SET amount=excluded.amount, plan=excluded.plan,"
            " promo_end=excluded.promo_end, note=excluded.note, recorded_at=excluded.recorded_at",
            (company, _date(period_end, "period_end"), amount, plan, _date(promo_end, "promo_end"), note, _now()),
        )
        self.db.commit()
        return {"company": company, "period_end": period_end, "amount": amount}

    @_locked
    def bills(self, company: str | None = None) -> list[dict]:
        if company:
            rows = self.db.execute("SELECT * FROM bills WHERE company=? ORDER BY period_end", (company,))
        else:
            rows = self.db.execute("SELECT * FROM bills ORDER BY company, period_end")
        return [dict(r) for r in rows]

    @_locked
    def check_bills(self, company: str | None = None, threshold_pct: float = 10.0, min_increase: float = 3.0,
                    promo_window_days: int = 45, today: dt.date | None = None) -> list[dict]:
        today = today or dt.date.today()
        by_company: dict[str, list[dict]] = {}
        for b in self.bills(company):
            by_company.setdefault(b["company"], []).append(b)
        findings = []
        for comp, rows in by_company.items():
            latest = rows[-1]
            history = rows[-4:-1]
            if history:
                baseline = statistics.median(b["amount"] for b in history)
                delta = latest["amount"] - baseline
                if baseline > 0 and delta >= min_increase and delta / baseline * 100 >= threshold_pct:
                    findings.append({
                        "company": comp, "kind": "increase", "period_end": latest["period_end"],
                        "amount": latest["amount"], "baseline": round(baseline, 2),
                        "increase": round(delta, 2), "increase_pct": round(delta / baseline * 100, 1),
                        "suggested_issue": "bill_increase",
                    })
            promo = next((b["promo_end"] for b in reversed(rows) if b["promo_end"]), None)
            if promo:
                days = (dt.date.fromisoformat(promo) - today).days
                if -30 <= days <= promo_window_days:
                    findings.append({
                        "company": comp, "kind": "promo_ending" if days >= 0 else "promo_ended",
                        "promo_end": promo, "days": days, "suggested_issue": "price_negotiation",
                    })
        return findings

    # ---- registry feedback --------------------------------------------------

    @_locked
    def report_problem(self, entity: str, problem: str, location: str | None = None) -> dict:
        _check_sensitive(problem)
        cur = self.db.execute(
            "INSERT INTO feedback(entity, location, problem, reported_at) VALUES(?,?,?,?)",
            (entity, location, problem, _now()),
        )
        self.db.commit()
        return {"id": cur.lastrowid, "entity": entity, "location": location, "problem": problem}

    @_locked
    def feedback(self) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM feedback ORDER BY id")]
