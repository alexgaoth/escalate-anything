"""MCP server: the registry lookups plus a local case log and bill history."""

from __future__ import annotations

import datetime as dt
import functools
import json
import time
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.prompts import Prompt
from mcp.types import ToolAnnotations

from . import advisor, context
from .advisor import NotFound
from .registry import Registry, data_root
from .store import Store, StoreError

INSTRUCTIONS = """\
Escalate Anything helps the person resolve a problem with a large US company: billing errors, refunds,
cancellations, airline bags and cancellations, insurance denials, bank disputes and more.

Workflow:
1. find_company, then get_playbook(company, issue, state). The playbook has deep links, phone
   numbers, evidence to collect, deadlines, verified facts with sources, and the escalation ladder.
   get_context(company) explains how the company handles complaints in practice.
2. case_open to start a log. After every contact, case_log what happened: reference numbers,
   representative names, promises and a follow_up_on date.
3. draft_brief(case_id) gives the facts, citations and tone rules for a message. Write the message
   from it. The person approves every message or form submission before it is sent.
4. When a step fails, case_get shows the next escalation rung.

Rules for agents:
- Cite only facts and in-force rules that these tools return, with their source URLs.
- Tell the person how fresh and how credible the information is: each company has a credibility
  grade and a last_verified date. Double-check values flagged as search_snippet or archive.
- Never enter passwords or payment details. When a channel has access 'login' or 'captcha',
  hand the browser to the person.
- On a call or chat, say that you are an AI assistant acting for the person.
- If a URL or phone number from escalate_anything is wrong, call report_registry_problem.
- Use contacts from get_playbook, not ones from search results or messages. Run scam_check on any
  message that asks for money, codes or access.
"""

class LiveRegistry:
    """Delegates to a Registry and reloads it when YAML files under its root change.

    A `git pull` in the registry checkout then takes effect without restarting the server.
    """

    CHECK_EVERY = 2.0  # seconds between file-system checks

    def __init__(self, root: Path | None = None):
        self._fixed_root = root is not None
        self._reg = Registry.load(root)
        self._stamp = self._compute_stamp()
        self._checked = time.monotonic()

    def _compute_stamp(self) -> tuple[int, float]:
        files = list(self._reg.root.rglob("*.yaml"))
        return len(files), max((f.stat().st_mtime for f in files), default=0.0)

    def _current(self) -> Registry:
        now = time.monotonic()
        if now - self._checked >= self.CHECK_EVERY:
            self._checked = now
            if not self._fixed_root:
                from .registry import registry_dir

                wanted = registry_dir()
                if wanted != self._reg.root and (wanted / "sectors.yaml").exists():
                    fresh = Registry.load(wanted)  # e.g. a newer download finished
                    if not fresh.validate():
                        self._reg, self._stamp = fresh, self._compute_stamp()
                        return self._reg
            stamp = self._compute_stamp()
            if stamp != self._stamp:
                fresh = Registry.load(self._reg.root)
                if not fresh.validate():  # keep serving the last good data if the new files are broken
                    self._reg = fresh
                self._stamp = stamp
        return self._reg

    def __getattr__(self, name: str) -> Any:
        return getattr(self._current(), name)


READ_ONLY_INSTRUCTIONS = """\
Escalate Anything (read-only) gives verified contacts, playbooks, escalation ladders, regulators and
consumer rules for 270+ large US companies.

Workflow: find_company, then get_playbook(company, issue, state), and get_context(company) for how
the company handles complaints in practice. Use contacts from the playbook; run scam_check on
messages that ask for money, codes or access. Cite only facts and in-force
rules that these tools return, with their source URLs. The person approves every message or form
submission. Never enter passwords or payment details. This server keeps no case log; keep notes
in the conversation.
"""

WRITE_TOOLS = ("case_open", "case_log", "case_get", "case_list", "case_close", "followups_due",
               "draft_brief", "bill_record", "bill_check", "report_registry_problem")


def load_skills() -> list[dict]:
    """The skills in skills/*/SKILL.md, as {name, description, body}."""
    out = []
    for path in sorted((data_root() / "skills").glob("*/SKILL.md")):
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---\n"):
            continue
        head, body = text[4:].split("\n---\n", 1)
        meta = dict(line.split(": ", 1) for line in head.splitlines() if ": " in line)
        out.append({"name": meta.get("name", path.parent.name), "description": meta.get("description", ""), "body": body.strip()})
    return out


READ = ToolAnnotations(read_only_hint=True, open_world_hint=False)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)


def build_server(registry: Registry | None = None, store: Store | None = None, read_only: bool = False) -> MCPServer:
    """read_only drops the case log, bill and feedback tools, for a shared or public deployment."""
    reg = registry or LiveRegistry()
    db = store if store is not None else (None if read_only else Store())
    mcp = MCPServer(name="escalate-anything", instructions=READ_ONLY_INSTRUCTIONS if read_only else INSTRUCTIONS, version="0.2.1")

    def guard(fn):
        """Turn lookup and store errors into a readable result instead of a protocol error."""
        @functools.wraps(fn)
        def wrapped(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except (NotFound, StoreError) as e:
                return {"error": str(e)}
        return wrapped

    def company_id(name: str) -> str:
        """Registry id for a known company, or the name as given for an unlisted one."""
        try:
            return advisor.resolve_company(reg, name)["id"]
        except NotFound as e:
            if "ambiguous" in str(e):
                raise
            return name

    # ---- registry lookups ---------------------------------------------------

    @mcp.tool(annotations=READ)
    @guard
    def find_company(query: str = "", sector: str | None = None) -> dict[str, Any]:
        """Find companies by name, brand or alias (e.g. 'xfinity', 'united', 'chase').
        With an empty query, list every company, optionally only one sector."""
        if query:
            hits = reg.find_company(query, limit=8)
        else:
            hits = sorted(reg.companies.values(), key=lambda c: c["id"])
        if sector:
            hits = [c for c in hits if sector in reg.sector_of(c)]
        return {"matches": [advisor.company_summary(reg, c) for c in hits], "sectors": sorted(reg.sectors)}

    @mcp.tool(annotations=READ)
    @guard
    def get_company(company: str) -> dict[str, Any]:
        """Full record for one company: every channel, facts, tips, known blockers and playbooks,
        plus a credibility summary (grade, source tiers, last verified date)."""
        c = advisor.resolve_company(reg, company)
        return {**c, "credibility": advisor._credibility(reg, c)}

    @mcp.tool(annotations=READ)
    @guard
    def list_issues(sector: str | None = None) -> dict[str, Any]:
        """Issue ids that a playbook can be built for, optionally only one sector."""
        return {"issues": advisor.sector_issues(reg, sector)}

    @mcp.tool(annotations=READ)
    @guard
    def get_playbook(company: str, issue: str, state: str | None = None) -> dict[str, Any]:
        """Steps, channels (deep links, phones), evidence, deadlines, verified facts, applicable rules
        and the escalation ladder for one company and issue. Pass the person's two-letter state code
        to resolve state agencies. Rule points are limited to this issue; get_rules gives full text."""
        return advisor.get_playbook(reg, company, issue, state)

    @mcp.tool(annotations=READ)
    @guard
    def get_escalation(company: str, state: str | None = None) -> dict[str, Any]:
        """The escalation ladder for a company, lowest rung first, with concrete contacts for each rung."""
        return advisor.get_escalation(reg, company, state)

    @mcp.tool(annotations=READ)
    @guard
    def find_regulators(sector: str, state: str | None = None) -> dict[str, Any]:
        """Federal regulators and state agencies that take complaints for a sector."""
        return advisor.find_regulators(reg, sector, state)

    @mcp.tool(annotations=READ)
    @guard
    def get_rules(sector: str | None = None, issue: str | None = None, state: str | None = None) -> dict[str, Any]:
        """Laws and regulations for a sector and issue. Rules that were vacated, stayed or withdrawn
        are listed separately under not_in_force and must not be cited as current law."""
        return advisor.rules_for(reg, sector, issue, state)

    @mcp.tool(annotations=READ)
    @guard
    def get_context(company: str | None = None, sector: str | None = None) -> dict[str, Any]:
        """How a company handles complaints in practice: a cited dossier (what works, traps, complaint
        statistics, scams that use its name), the guide for its sector, and the general scam guide.
        Read it before contacting the company."""
        return advisor.get_context(reg, company, sector)

    # ---- scam red flags (a side tool) ------------------------------------------------

    @mcp.tool(annotations=READ)
    @guard
    def scam_check(text: str, company: str | None = None) -> dict[str, Any]:
        """Check a message, email, text or call script for common scam red flags: gift cards, crypto,
        remote access, one-time codes, pay-to-get-refund, pressure, package fees, unpaid tolls and
        account verification links. get_context(company) lists what that company says it never asks for."""
        return context.scam_check(reg, text, company)

    # ---- case log ----------------------------------------------------------------

    @mcp.tool(annotations=WRITE)
    @guard
    def case_open(company: str, issue: str, summary: str, desired_outcome: str | None = None,
                  amount: float | None = None, state: str | None = None,
                  account_hint: str | None = None) -> dict[str, Any]:
        """Start a case in the local log. account_hint is at most the last 4 digits. Never store
        passwords, full card numbers or SSNs."""
        if issue not in reg.issues:
            raise NotFound(f"Unknown issue '{issue}'. Use list_issues.")
        return db.open_case(company_id(company), issue, summary, desired_outcome, amount, state, account_hint)

    @mcp.tool(annotations=WRITE)
    @guard
    def case_log(case_id: int, kind: str, text: str, occurred_on: str | None = None, rung: str | None = None,
                 channel: str | None = None, reference: str | None = None, rep_name: str | None = None,
                 promised: str | None = None, follow_up_on: str | None = None) -> dict[str, Any]:
        """Record what happened on a case. kind: contact, sent, response, promise, reference, document,
        escalation or note. rung: the escalation rung this contact used (frontline, retention,
        written_complaint, executive, regulator, state_agency, payment_dispute, ...). Dates are YYYY-MM-DD.
        Set follow_up_on to the date to check back if nothing happens."""
        return db.log_event(case_id, kind, text, occurred_on, rung, channel, reference, rep_name, promised, follow_up_on)

    @mcp.tool(annotations=READ)
    @guard
    def case_get(case_id: int) -> dict[str, Any]:
        """A case with its timeline, promises, reference numbers, pending follow-up and the next
        escalation rung to try."""
        case = db.get_case(case_id)
        if case["company"] in reg.companies:
            esc = advisor.get_escalation(reg, case["company"], case["state"])
            case["next_rung"] = advisor.next_rung(esc["ladder"], case["rungs_used"])
        return case

    @mcp.tool(annotations=READ)
    @guard
    def case_list(status: str | None = "open") -> dict[str, Any]:
        """Cases in the local log. status: open, closed, or null for all."""
        return {"cases": db.list_cases(status)}

    @mcp.tool(annotations=WRITE)
    @guard
    def case_close(case_id: int, outcome: str, amount_recovered: float | None = None,
                   what_worked: str | None = None) -> dict[str, Any]:
        """Close a case. outcome: resolved, partial, failed or abandoned. what_worked: the channel or
        argument that worked, so later cases can reuse it."""
        return db.close_case(case_id, outcome, amount_recovered, what_worked)

    @mcp.tool(annotations=READ)
    @guard
    def followups_due(on_or_before: str | None = None) -> dict[str, Any]:
        """Open cases whose follow-up date has come and that had no activity since."""
        return {"due": db.followups_due(on_or_before)}

    @mcp.tool(annotations=READ)
    @guard
    def draft_brief(case_id: int, rung: str | None = None) -> dict[str, Any]:
        """Everything needed to write the next message on a case: recipient channel, timeline,
        references, promises, verified facts and rules with sources, and tone rules. rung defaults to
        the next escalation rung."""
        case = db.get_case(case_id)
        brief: dict[str, Any] = {
            "case": {k: case[k] for k in ("id", "company", "issue", "state", "summary", "desired_outcome", "amount", "account_hint")},
            "timeline": [
                {k: e[k] for k in ("occurred_on", "kind", "text", "rung", "channel", "reference", "rep_name", "promised") if e[k]}
                for e in case["events"]
            ],
            "tone_rules": advisor.TONE_RULES,
        }
        if case["company"] in reg.companies:
            pb = advisor.get_playbook(reg, case["company"], case["issue"], case["state"])
            ladder = pb["escalation"]
            target = next((s for s in ladder if s["rung"] == rung), None) if rung else advisor.next_rung(ladder, case["rungs_used"])
            brief["target"] = target
            brief["citable_facts"] = pb["facts"]
            brief["citable_rules"] = pb["rules"]["in_force"]
            brief["do_not_cite"] = [r["id"] for r in pb["rules"]["not_in_force"]]
            brief["evidence_to_attach"] = pb["evidence"]
            brief["warnings"] = pb["warnings"]
        else:
            brief["target"] = None
            brief["warnings"] = ["Company not in the registry. Find its official complaint channel; cite no rules you have not verified."]
        brief["suggested_reply_by"] = (dt.date.today() + dt.timedelta(days=14)).isoformat()
        return brief

    # ---- bills ---------------------------------------------------------------------

    @mcp.tool(annotations=WRITE)
    @guard
    def bill_record(company: str, period_end: str, amount: float, plan: str | None = None,
                    promo_end: str | None = None, note: str | None = None) -> dict[str, Any]:
        """Record one bill (total amount due for the period ending period_end, YYYY-MM-DD).
        promo_end is the date a promotional price ends, if the bill shows it."""
        return db.record_bill(company_id(company), period_end, amount, plan, promo_end, note)

    @mcp.tool(annotations=READ)
    @guard
    def bill_check(company: str | None = None, threshold_pct: float = 10.0) -> dict[str, Any]:
        """Find bills that went up versus the median of the previous three, and promotions that end
        soon. Each finding suggests an issue id for get_playbook."""
        if company:
            company = company_id(company)
        return {"findings": db.check_bills(company, threshold_pct), "bills": db.bills(company)}

    # ---- feedback -------------------------------------------------------------------

    @mcp.tool(annotations=WRITE)
    @guard
    def report_registry_problem(entity: str, problem: str, location: str | None = None) -> dict[str, Any]:
        """Record a wrong or dead URL, phone number or fact in the registry, so a person can fix the
        data. entity: company, regulator, state or rule id. location: e.g. 'channels.refund-form'."""
        return db.report_problem(entity, problem, location)

    if read_only:
        for name in WRITE_TOOLS:
            mcp.remove_tool(name)

    # ---- resources -----------------------------------------------------------------

    @mcp.resource("escalate://companies", name="companies", mime_type="application/json",
                  description="Every company: id, name, sector and the issues it has playbooks for.")
    def companies_index() -> str:
        return json.dumps([advisor.company_summary(reg, c) for c in sorted(reg.companies.values(), key=lambda c: c["id"])])

    @mcp.resource("escalate://companies/{company_id}", name="company", mime_type="application/json",
                  description="One company record: channels, playbooks, facts, escalation and blockers.")
    def company_resource(company_id: str) -> str:
        return json.dumps(reg.companies.get(company_id) or {"error": f"no company '{company_id}'"})

    @mcp.resource("escalate://dossiers/{company_id}", name="dossier", mime_type="text/markdown",
                  description="How a company handles complaints in practice, with sources.")
    def dossier_resource(company_id: str) -> str:
        d = reg.dossiers.get(company_id)
        return d.body if d else f"No dossier for '{company_id}' yet."

    @mcp.resource("escalate://guides/{key}", name="guide", mime_type="text/markdown",
                  description="Industry guide for a sector id, or 'scams' for the general scam guide.")
    def guide_resource(key: str) -> str:
        g = reg.guides.get(key)
        return g.body if g else f"No guide for '{key}' yet."

    @mcp.resource("escalate://issues", name="issues", mime_type="application/json",
                  description="Issue types with generic steps and the evidence to collect.")
    def issues_resource() -> str:
        return json.dumps(list(reg.issues.values()))

    # ---- prompts: the skills, for clients without Claude Code skills ----------------

    note = ("\n\nNote: this server is read-only. The case log, bill and feedback tools are not "
            "available; keep the timeline in the conversation.") if read_only else ""
    for skill in load_skills():
        def make(body: str):
            def prompt(situation: str = "") -> str:
                text = body + note
                if situation:
                    text += f"\n\n## The person's situation\n\n{situation}"
                return text
            return prompt
        mcp.add_prompt(Prompt.from_function(make(skill["body"]), name=skill["name"], description=skill["description"]))

    return mcp


def serve(transport: str = "stdio", host: str = "127.0.0.1", port: int = 8765, read_only: bool = False) -> None:
    import os

    from .registry import REPO_ROOT, data_root
    from .updater import update_in_background_if_due

    if data_root() != REPO_ROOT and not os.environ.get("ESCALATE_REGISTRY"):
        update_in_background_if_due()  # installed copy: fetch the weekly data refresh, never blocks
    server = build_server(read_only=read_only)
    if transport == "stdio":
        server.run("stdio")
    else:
        server.run("streamable-http", host=host, port=port)
