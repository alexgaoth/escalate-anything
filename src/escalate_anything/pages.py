"""Static, indexable HTML pages, so search engines and AI search can find and cite each playbook.

build_site() calls build_pages(). Output, next to the single-page app:

    c/<company-id>/index.html               company: contacts, playbooks, escalation path, dossier
    c/<company-id>/<issue-slug>/index.html  one playbook (issue id with "_" changed to "-")
    issues/<issue-slug>/index.html          issue hub: generic steps and every company playbook for it
    guides/<key>/index.html                 a sector guide or the scam guide, rendered from Markdown
    assets/pages.css                        the stylesheet for these pages
    sitemap.xml, robots.txt

The pages show what the MCP tools return: company_document() resolves each playbook with get_playbook()
and the escalation ladder with get_escalation(). The pages use no JavaScript. Links between pages are
relative, so the site works under a subpath; canonical, Open Graph and sitemap URLs are absolute.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit
from xml.sax.saxutils import escape as xml_escape

from .registry import Registry

WEB_DIR = Path(__file__).with_name("web")
SITE_NAME = "Escalate Anything"
TITLE_MAX = 65
DESCRIPTION_MAX = 160
STALE_AFTER_DAYS = 365
CC_BY = "https://creativecommons.org/licenses/by/4.0/"
DOSSIER_NOTE = ("Every point links to its source. “Reported by customers” marks an anecdote from a forum: "
                "a tactic to try, not a fact to quote.")

TYPE = {"phone": "Phone", "sms": "Text", "chat": "Chat", "web_form": "Form", "portal": "Online", "email": "Email",
        "app": "App", "mail": "Mail", "in_person": "In person", "social": "Social", "fax": "Fax"}
GROUP = {"phone": "Phone", "sms": "Text message", "chat": "Chat", "web_form": "Online forms",
         "portal": "Online tools and accounts", "email": "Email", "app": "Apps", "mail": "Mail",
         "in_person": "In person", "social": "Social media", "fax": "Fax"}
ACCESS = {"login": ("Sign-in required", ""), "captcha": ("CAPTCHA", "warn"), "human_only": ("Account holder only", "warn")}
RUNG = {"frontline": "Customer service", "supervisor": "Supervisor", "retention": "Retention team",
        "written_complaint": "Written complaint", "executive": "Executive office", "regulator": "Federal regulator",
        "state_agency": "State agency", "payment_dispute": "Card or bank dispute", "arbitration": "Arbitration",
        "small_claims": "Small claims court", "public": "Public complaint"}
AGENCY = {"attorney_general": "attorney general", "utility_commission": "utility commission",
          "insurance_department": "insurance department", "financial_regulator": "financial regulator",
          "consumer_affairs": "consumer affairs office"}
FACT = {"deadline": "Deadline", "policy": "Policy", "compensation": "Compensation", "process": "Process",
        "limit": "Limit", "contact": "Contact", "fee": "Fee"}
STATUS = {"partially_in_effect": "Partly in effect", "stayed": "Stayed", "vacated": "Vacated", "repealed": "Repealed",
          "proposed": "Proposed", "withdrawn": "Withdrawn", "superseded": "Superseded"}

# The example request in the "Let your AI agent handle this" box. {c} is the company name.
ASK = {
    "billing_error": "{c} charged me [amount] on [date] for something I did not order. Use Escalate Anything to get it corrected.",
    "bill_increase": "My {c} bill went from [old amount] to [new amount]. Use Escalate Anything to get it back down.",
    "unauthorized_charge": "{c} charged me [amount] on [date] and I did not authorize it. Use Escalate Anything to get it reversed.",
    "cancel_service": "I cancelled {c} on [date] and they still charge me. Use Escalate Anything to stop it and get refunded.",
    "refund_request": "{c} owes me a refund of [amount] for [order or service]. Use Escalate Anything to get it.",
    "price_negotiation": "I pay {c} [amount] a month. Use Escalate Anything to get the price down.",
    "poor_service": "{c} promised [what] on [date] and did not deliver. Use Escalate Anything to hold them to it.",
    "service_outage": "My {c} service was down from [date] to [date]. Use Escalate Anything to get a credit.",
    "equipment_return": "I returned my {c} equipment on [date] and they still charged me. Use Escalate Anything to get the charge removed.",
    "number_port_out": "{c} is blocking my number transfer. Use Escalate Anything to get it moved.",
    "device_unlock": "{c} will not unlock my paid-off phone. Use Escalate Anything to get it unlocked.",
    "trade_in_credit": "{c} never applied my [amount] trade-in credit. Use Escalate Anything to get it.",
    "early_termination_fee": "{c} charged me an early termination fee of [amount]. Use Escalate Anything to dispute it.",
    "free_trial_conversion": "{c} charged me [amount] after a free trial on [date]. Use Escalate Anything to get a refund.",
    "slamming": "My service was switched to {c} without my permission. Use Escalate Anything to undo it and get refunded.",
    "account_access": "I am locked out of my {c} account. Use Escalate Anything to get back in.",
    "privacy_request": "I want {c} to delete my data. Use Escalate Anything to make the request.",
    "debt_collection": "{c} sent a bill I [paid or dispute] to collections. Use Escalate Anything to fix it.",
    "company_shutdown": "{c} shut down and owes me [amount]. Use Escalate Anything to get my money back.",
    "flight_cancellation": "{c} cancelled my flight on [date]. Use Escalate Anything to get me a refund.",
    "flight_delay": "My {c} flight on [date] was [hours] late. Use Escalate Anything to get what I am owed.",
    "denied_boarding": "{c} bumped me from my flight on [date]. Use Escalate Anything to get my compensation.",
    "delayed_baggage": "{c} lost my bag on [date and flight]. Use Escalate Anything to get me reimbursed.",
    "lost_baggage": "{c} lost my bag on [date and flight] and it never came back. Use Escalate Anything to get me paid.",
    "damaged_baggage": "{c} damaged my bag on [date and flight]. Use Escalate Anything to get it paid for.",
    "ancillary_fee_refund": "I paid {c} [amount] for [seat, Wi-Fi or bag] and did not get it. Use Escalate Anything to get a refund.",
    "travel_credit": "{c} gave me a credit instead of a refund for [trip]. Use Escalate Anything to get my money back.",
    "accessibility": "{c} did not provide the assistance I booked on [date]. Use Escalate Anything to file a complaint.",
    "event_cancelled": "My [event] tickets from {c} were cancelled. Use Escalate Anything to get a refund.",
    "account_transfer": "{c} is blocking my transfer of [amount]. Use Escalate Anything to get it released.",
    "lost_package": "My {c} package shows delivered but never arrived. Use Escalate Anything to get a refund or a replacement.",
    "damaged_item": "My {c} order arrived broken on [date]. Use Escalate Anything to get a refund or a replacement.",
    "late_delivery": "My {c} delivery missed its guaranteed time on [date]. Use Escalate Anything to get the refund.",
    "price_adjustment": "I bought [item] from {c} and the price dropped. Use Escalate Anything to get the difference back.",
    "lost_item": "I left [item] behind with {c} on [date]. Use Escalate Anything to get it back.",
    "safety_incident": "Something unsafe happened with {c} on [date]. Use Escalate Anything to report it.",
    "warranty_claim": "My {c} [product] broke under warranty. Use Escalate Anything to get it repaired or replaced.",
    "claim_denial": "{c} denied my claim for [what]. Use Escalate Anything to appeal it.",
    "claim_delay": "{c} has not paid my claim from [date]. Use Escalate Anything to push it forward.",
    "surprise_medical_bill": "I got a surprise bill for [amount] with {c} coverage. Use Escalate Anything to dispute it.",
    "fee_reversal": "{c} charged me a [type] fee of [amount]. Use Escalate Anything to get it reversed.",
    "transaction_dispute": "A merchant did not deliver, and I paid with my {c} card. Use Escalate Anything to dispute the charge.",
    "fraud": "I lost [amount] to a scam through {c} on [date]. Use Escalate Anything to try to get it back.",
    "frozen_funds": "{c} froze my account with [amount] in it. Use Escalate Anything to get my money released.",
    "identity_theft": "Someone opened a {c} account in my name. Use Escalate Anything to close it and clean up.",
    "credit_report_error": "My {c} credit report shows [wrong item]. Use Escalate Anything to get it corrected.",
    "student_loan_servicing": "{c} got my student loan payment wrong. Use Escalate Anything to fix it.",
    "repayment_plan": "{c} has not processed my repayment plan request from [date]. Use Escalate Anything to push it forward.",
    "transfer_cancellation": "My {c} transfer of [amount] on [date] never arrived. Use Escalate Anything to get it back.",
    "money_order": "My {c} money order for [amount] was lost. Use Escalate Anything to get a refund.",
    "damage_claim": "{c} charged me [amount] for damage I did not cause. Use Escalate Anything to dispute it.",
    "deposit_refund": "{c} has not returned my [amount] deposit. Use Escalate Anything to get it back.",
    "reservation_problem": "{c} did not honor my reservation for [date]. Use Escalate Anything to get compensated.",
    "payment_assistance": "I cannot pay my full {c} bill this month. Use Escalate Anything to find a payment plan or help.",
    "property_damage_claim": "{c} damaged my [property] on [date]. Use Escalate Anything to file a claim.",
    "disconnection": "{c} says it will disconnect my service on [date]. Use Escalate Anything to stop it.",
}
ASK_DEFAULT = "My problem with {c}: [what happened, with dates and amounts]. Use Escalate Anything to get it resolved."


# ---- paths -------------------------------------------------------------------


def issue_slug(issue: str) -> str:
    return issue.replace("_", "-")


def company_path(cid: str) -> str:
    return f"c/{cid}/"


def playbook_path(cid: str, issue: str) -> str:
    return f"c/{cid}/{issue_slug(issue)}/"


def issue_path(issue: str) -> str:
    return f"issues/{issue_slug(issue)}/"


def guide_path(key: str) -> str:
    return f"guides/{key}/"


@dataclass
class Page:
    path: str  # relative to the site root, with a trailing slash
    title: str
    description: str
    crumbs: list[tuple[str, str]]  # (name, path) after Home; the last one is this page
    body: str
    lastmod: str | None
    company: str | None = None  # prefills the data-correction form
    json: str | None = None  # the same data as JSON, for agents
    og_type: str = "article"


# ---- entry point -------------------------------------------------------------


def build_pages(out: Path, reg: Registry, docs: dict[str, dict], base_url: str, repo_url: str,
                today: dt.date) -> dict[str, int]:
    """Write every static page, assets/pages.css, sitemap.xml and robots.txt. docs: company_document() by id."""
    ctx = _Ctx(reg, base_url, repo_url, today)
    pages: list[Page] = []
    dates: dict[str, list[str]] = {}  # playbook dates by issue, for the issue hubs
    for doc in docs.values():
        for issue, pb in doc["playbooks"].items():
            page = playbook_page(ctx, doc, issue, pb)
            pages.append(page)
            if page.lastmod:
                dates.setdefault(issue, []).append(page.lastmod)
        pages.append(company_page(ctx, doc))
    for iid in reg.issues:
        pages.append(issue_page(ctx, iid, docs, max(dates.get(iid, []), default=None)))
    for key in sorted(reg.guides):
        pages.append(guide_page(ctx, key))

    (out / "assets").mkdir(parents=True, exist_ok=True)
    (out / "assets" / "pages.css").write_text(stylesheet(), encoding="utf-8")
    for page in pages:
        target = out / page.path / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render(ctx, page), encoding="utf-8")

    newest = max((p.lastmod for p in pages if p.lastmod), default=None)
    (out / "sitemap.xml").write_text(sitemap([("", newest)] + [(p.path, p.lastmod) for p in pages], base_url), encoding="utf-8")
    (out / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {base_url}sitemap.xml\n", encoding="utf-8")
    kinds = {"playbook_pages": 0, "company_pages": 0, "issue_pages": 0, "guide_pages": 0}
    for p in pages:
        kinds[_kind(p.path) + "_pages"] += 1
    return kinds


def _kind(path: str) -> str:
    if path.startswith("c/"):
        return "playbook" if path.count("/") == 3 else "company"
    return "issue" if path.startswith("issues/") else "guide"


class _Ctx:
    def __init__(self, reg: Registry, base_url: str, repo_url: str, today: dt.date):
        self.reg = reg
        self.base = base_url
        self.repo = repo_url
        self.today = today
        self.by_issue: dict[str, list[str]] = {}
        for c in sorted(reg.companies.values(), key=lambda c: c["name"].lower()):
            for pb in c.get("playbooks", []):
                self.by_issue.setdefault(pb["issue"], []).append(c["id"])

    def issue_name(self, iid: str) -> str:
        i = self.reg.issues.get(iid)
        return i["name"] if i else iid.replace("_", " ").capitalize()

    def sector_name(self, sid: str) -> str:
        s = self.reg.sectors.get(sid)
        return s["name"] if s else sid.replace("_", " ").capitalize()


# ---- page: playbook ----------------------------------------------------------


def playbook_page(ctx: _Ctx, doc: dict, issue: str, pb: dict) -> Page:
    c = doc["company"]
    name, iname = c["name"], ctx.issue_name(issue)
    lower = _lower_first(iname)
    path = playbook_path(c["id"], issue)
    r = _root(path)
    channels = c.get("channels", [])

    in_steps = set()
    steps = []
    for st in pb["steps"]:
        parts = [f'<p>{escape(st["do"])}</p>']
        if st.get("note"):
            parts.append(f'<p class="step-note">{escape(st["note"])}</p>')
        if st.get("channel"):
            in_steps.add(st["channel"]["id"])
            parts.append(channel_line(st["channel"]))
        if st.get("regulator"):
            parts.append(regulator_line(st["regulator"]))
        steps.append(f'<li>{"".join(parts)}</li>')
    more = [ch for ch in pb["channels"] if ch["id"] not in in_steps and issue in (ch.get("purposes") or [])]
    rules = pb["rules"]
    warnings = [w for w in pb.get("warnings", []) if not w.startswith("No ")]
    others = [p["issue"] for p in c.get("playbooks", []) if p["issue"] != issue]
    cred = pb["credibility"]

    body = [
        _head(name + ": " + lower, None),
        f'<p class="answer">{escape(pb.get("summary") or "")}</p>' if pb.get("summary") else "",
        cred_line(cred),
        '<div class="actions">'
        f'<a class="btn" href="{r}{company_path(c["id"])}">All {escape(name)} contacts</a>'
        f'<a class="btn" href="{r}#/c/{escape(c["id"])}/{escape(issue)}">Open in the interactive directory</a>'
        f'<a class="btn" href="{r}companies/{escape(c["id"])}.json">JSON</a></div>',
    ]
    if pb.get("evidence"):
        body.append(_section("Collect", f'<ul class="list">{"".join(f"<li>{escape(e)}</li>" for e in pb["evidence"])}</ul>'))
    body.append(_section("Steps", f'<ol class="steps">{"".join(steps)}</ol>'))
    if more:
        body.append(_section("More contacts for this issue", "".join(channel_line(ch) for ch in more)))
    if pb.get("facts"):
        body.append(_section("Facts you can cite", f'<ul class="facts">{"".join(fact_html(f, ctx.today) for f in pb["facts"])}</ul>'))
    if pb.get("tips"):
        body.append(_section("Tips", f'<ul class="facts">{"".join(tip_html(t, ctx.today) for t in pb["tips"])}</ul>'))
    if rules["in_force"]:
        body.append(_section("Rules in force", f'<ul class="rules">{"".join(rule_html(x, ctx.today) for x in rules["in_force"])}</ul>'))
    if rules["not_in_force"]:
        body.append(_section("Rules not in force (do not cite)", f'<ul class="rules">{"".join(rule_html(x, ctx.today) for x in rules["not_in_force"])}</ul>'))
    body.append(_section("If that fails, escalate",
                         '<p class="notes" style="margin-bottom:14px">Go up one step at a time. Keep the reference numbers and dates from each contact.</p>'
                         + ladder_html(ctx, pb["escalation"], channels, c["sector"], r)))
    if pb.get("known_blockers"):
        body.append(_section("Watch out", f'<div class="box warn"><ul class="list">{"".join(f"<li>{escape(b)}</li>" for b in pb["known_blockers"])}</ul></div>'))
    if warnings:
        body.append(_section("Check before you rely on it", f'<div class="box warn"><ul class="list">{"".join(f"<li>{escape(w)}</li>" for w in warnings)}</ul></div>'))
    body.append(cta(ctx, ASK.get(issue, ASK_DEFAULT).format(c=name)))

    related = [f'<li><a href="{r}{issue_path(issue)}">{escape(iname)} at other companies</a></li>']
    if doc.get("dossier"):
        related.append(f'<li><a href="{r}{company_path(c["id"])}#dossier">How {escape(name)} complaints actually go</a> (dossier, checked {escape(doc["dossier"]["last_verified"])})</li>')
    if doc.get("guide"):
        related.append(f'<li><a href="{r}{guide_path(doc["guide"]["key"])}">{escape(doc["guide"]["title"] or ctx.sector_name(c["sector"]))}</a></li>')
    related += [f'<li><a href="{r}{playbook_path(c["id"], o)}">{escape(name)}: {escape(_lower_first(ctx.issue_name(o)))}</a></li>' for o in others]
    body.append(_section("Related", f'<ul class="links">{"".join(related)}</ul>'))

    summary = pb.get("summary") or ""
    return Page(
        path=path,
        title=_fit([f"{n} {lower}: {tail}" for n in (name, _short_name(name)) for tail in ("steps, contacts and escalation", "what to do")]
                   + [f"{_short_name(name)}: {lower}"], TITLE_MAX),
        description=_fit([f"{name} {lower}: {_lower_first(summary)}" if summary else "", summary or f"{name} {lower}: steps, contacts and escalation."], DESCRIPTION_MAX),
        crumbs=[(name, company_path(c["id"])), (iname, path)],
        body="".join(body),
        lastmod=_newest({k: pb.get(k) for k in ("steps", "channels", "facts", "rules", "tips", "escalation")}),
        company=c["id"],
        json=f"companies/{c['id']}.json",
    )


# ---- page: company -----------------------------------------------------------


def company_page(ctx: _Ctx, doc: dict) -> Page:
    c = doc["company"]
    name = c["name"]
    path = company_path(c["id"])
    r = _root(path)
    issues = [p["issue"] for p in c.get("playbooks", [])]
    # Facts and tips that no playbook on this page shows.
    def covered(x: dict) -> bool:
        return not x.get("issues") or any(i in issues for i in x["issues"])

    other_facts = [f for f in c.get("facts", []) if issues and not covered(f)]
    other_tips = [t for t in c.get("tips", []) if issues and not covered(t)]

    meta = [ctx.sector_name(c["sector"])]
    if c.get("parent"):
        meta.append(f"Part of {c['parent']}")
    actions = []
    if _is_url(c.get("website")):
        actions.append(f'<a class="btn primary" href="{escape(c["website"])}">Website</a>')
    if _is_url(c.get("account_url")):
        actions.append(f'<a class="btn" href="{escape(c["account_url"])}">Sign in to your account</a>')
    actions.append(f'<a class="btn" href="{r}#/c/{escape(c["id"])}">Open in the interactive directory</a>')
    actions.append(f'<a class="btn" href="{r}companies/{escape(c["id"])}.json">JSON</a>')
    body = [_head(name, ". ".join(meta) + "."), cred_line(doc["credibility"]), f'<div class="actions">{"".join(actions)}</div>']

    if issues:
        items = []
        for i in issues:
            pb = doc["playbooks"].get(i) or {}
            items.append(f'<li><a href="{r}{playbook_path(c["id"], i)}">{escape(ctx.issue_name(i))}</a>'
                         f'{f"""<span class="sum">{escape(pb["summary"])}</span>""" if pb.get("summary") else ""}</li>')
        body.append(_section(f"Get help with ({len(issues)})", f'<ul class="links">{"".join(items)}</ul>'))
    body.append(_section(f"Contacts ({len(c.get('channels', []))})", channel_groups(ctx, c, r), "contacts"))
    body.append(_section("Escalation path",
                         '<p class="notes" style="margin-bottom:14px">Go up one step at a time. Keep the reference numbers and dates from each contact.</p>'
                         + ladder_html(ctx, doc["escalation"], c.get("channels", []), c["sector"], r)))
    if c.get("known_blockers"):
        body.append(_section("Known blockers", f'<div class="box warn"><ul class="list">{"".join(f"<li>{escape(b)}</li>" for b in c["known_blockers"])}</ul></div>'))
    body.append(security_html(ctx, c, doc["security"]))
    if doc.get("dossier"):
        d = doc["dossier"]
        body.append(_section(
            "How complaints actually go",
            f'<p class="notes" style="margin-bottom:12px">{escape(DOSSIER_NOTE)} Checked {escape(d["last_verified"])}. '
            f'Markdown: <a href="{r}{escape(d["file"])}">{escape(d["file"])}</a></p>'
            f'<div class="box md">{doc_html(d["markdown"], 3)}</div>', "dossier"))
    if doc.get("guide"):
        g = doc["guide"]
        body.append(f'<p class="notes" style="margin-top:12px">For the whole industry, read <a href="{r}{guide_path(g["key"])}">{escape(g["title"] or ctx.sector_name(g["key"]))}</a>.</p>')
    if other_facts or other_tips:
        body.append(_section("More facts", '<ul class="facts">' + "".join(fact_html(f, ctx.today) for f in other_facts)
                             + "".join(tip_html(t, ctx.today) for t in other_tips) + "</ul>"))
    if c.get("notes"):
        body.append(_section("Verification notes", f'<p class="notes">{escape(c["notes"])}</p>'))
    body.append(cta(ctx, ASK_DEFAULT.format(c=name)))

    listed = ", ".join(_lower_first(ctx.issue_name(i)) for i in issues[:4])
    n_ch = len(c.get("channels", []))
    return Page(
        path=path,
        title=_fit([f"{n} complaints: {tail}" for n in (name, _short_name(name))
                    for tail in ("contacts, playbooks and escalation", "contacts and escalation")]
                   + [f"{_short_name(name)} complaints"], TITLE_MAX),
        description=_fit([
            f"How to get {name} to fix a problem: {_plural(len(issues), 'playbook')}{' (' + listed + ')' if listed else ''}, "
            f"{_plural(n_ch, 'verified contact')} and the escalation path. Every value is sourced.",
            f"How to get {name} to fix a problem: {_plural(len(issues), 'playbook')}, {_plural(n_ch, 'verified contact')} and the escalation path.",
        ], DESCRIPTION_MAX),
        crumbs=[(name, path)],
        body="".join(body),
        lastmod=doc["credibility"].get("last_verified"),
        company=c["id"],
        json=f"companies/{c['id']}.json",
    )


def security_html(ctx: _Ctx, c: dict, s: dict) -> str:
    parts = []
    if s.get("official_domains"):
        parts.append('<h3>Official domains</h3><ul class="domains">'
                     + "".join(f"<li><code>{escape(d)}</code></li>" for d in s["official_domains"])
                     + f'</ul><p class="notes" style="margin-top:6px">Real links and emails from {escape(c["name"])} end in one of these.</p>')
    if s.get("never_asks"):
        parts.append(f'<h3>{escape(c["name"])} will never ask you for</h3><ul class="facts">'
                     + "".join(f'<li class="fact"><p>{escape(f["claim"])}</p>{src_html(f, ctx.today)}</li>' for f in s["never_asks"]) + "</ul>")
    if s.get("known_scams"):
        parts.append('<h3>Known scams</h3><ul class="facts">'
                     + "".join(f'<li class="fact"><p>{escape(f["claim"])}</p>{src_html(f, ctx.today)}</li>' for f in s["known_scams"]) + "</ul>")
    if s.get("report_phishing"):
        parts.append('<h3>Report phishing</h3><ul class="ch-list">' + "".join(channel_html(ctx, ch, "") for ch in s["report_phishing"]) + "</ul>")
    return _section("Scam warnings", f'<div class="box">{"".join(parts)}</div>', "scams") if parts else ""


# ---- page: issue hub ---------------------------------------------------------


def issue_page(ctx: _Ctx, iid: str, docs: dict[str, dict], lastmod: str | None) -> Page:
    i = ctx.reg.issues[iid]
    name = i["name"]
    path = issue_path(iid)
    r = _root(path)
    cids = ctx.by_issue.get(iid, [])
    body = [_head(f"{name}: what to do", None), f'<p class="lede">{escape(i.get("description", ""))}</p>']
    if i.get("evidence"):
        body.append(_section("Have this ready", f'<ul class="list">{"".join(f"<li>{escape(e)}</li>" for e in i["evidence"])}</ul>'))
    if i.get("steps"):
        body.append(_section("Steps for any company", f'<ol class="steps">{"".join(f"<li><p>{escape(_plain(s))}</p></li>" for s in i["steps"])}</ol>'
                             + '<p class="notes" style="margin-top:12px">A company playbook below replaces these generic steps with the company’s own forms, phone numbers and deadlines.</p>'))
    if cids:
        by_sector: dict[str, list[str]] = {}
        for cid in cids:
            by_sector.setdefault(docs[cid]["company"]["sector"], []).append(cid)
        groups = []
        for sid in sorted(by_sector, key=lambda s: ctx.sector_name(s).lower()):
            items = []
            for cid in by_sector[sid]:
                doc = docs[cid]
                summary = (doc["playbooks"].get(iid) or {}).get("summary")
                items.append(f'<li><a href="{r}{playbook_path(cid, iid)}">{escape(doc["company"]["name"])}</a>'
                             f'{f"""<span class="sum">{escape(summary)}</span>""" if summary else ""}</li>')
            heading = f"<h3>{escape(ctx.sector_name(sid))}</h3>" if len(by_sector) > 1 else ""
            groups.append(f'{heading}<ul class="links">{"".join(items)}</ul>')
        body.append(_section(f"Company playbooks ({len(cids)})", "".join(groups)))
    else:
        body.append(_section("Company playbooks", '<p class="notes">No company has its own playbook for this issue yet. '
                             f'Use the steps above with the company’s contacts: <a href="{r}">find the company</a>.</p>'))
    sectors = [s for s in i.get("sectors", []) if s in ctx.reg.guides]
    if sectors:
        body.append(_section("Guides", '<ul class="links">' + "".join(
            f'<li><a href="{r}{guide_path(s)}">{escape(str(ctx.reg.guides[s].meta.get("title") or ctx.sector_name(s)))}</a></li>' for s in sectors) + "</ul>"))
    body.append(cta(ctx, ASK.get(iid, ASK_DEFAULT).format(c="[company]")))

    examples = [docs[cid]["company"]["name"] for cid in cids[:3]]
    n = len(cids)
    return Page(
        path=path,
        title=_fit([f"{name}: what to do, with playbooks for {_plural(n, 'company', 'companies')}" if n else f"{name}: what to do and where to escalate",
                    f"{name}: what to do", name], TITLE_MAX),
        description=_fit([
            f"{i.get('description', '')} Steps, evidence and company playbooks for {_plural(n, 'company', 'companies')}, "
            f"including {', '.join(examples)}.",
            f"{i.get('description', '')} Steps, evidence and playbooks for {_plural(n, 'company', 'companies')}.",
        ] if n else [f"{i.get('description', '')} Steps, evidence to collect and where to escalate."], DESCRIPTION_MAX),
        crumbs=[(name, path)],
        body="".join(body),
        lastmod=lastmod,
        json="issues.json",
        og_type="website",
    )


# ---- page: guide -------------------------------------------------------------


def guide_page(ctx: _Ctx, key: str) -> Page:
    g = ctx.reg.guides[key]
    title = str(g.meta.get("title") or key)
    path = guide_path(key)
    r = _root(path)
    lv = str(g.meta.get("last_verified") or "")
    body = [_head(title, f"Checked {lv}. {DOSSIER_NOTE}" if lv else DOSSIER_NOTE),
            f'<article class="md" style="margin-top:24px">{doc_html(g.body, 2)}</article>']
    sector = g.meta.get("sector")
    companies = sorted((c for c in ctx.reg.companies.values() if c["sector"] == sector), key=lambda c: c["name"].lower())
    if companies:
        body.append(_section(f"Companies ({len(companies)})", '<ul class="inline">' + "".join(
            f'<li><a href="{r}{company_path(c["id"])}">{escape(c["name"])}</a></li>' for c in companies) + "</ul>"))
    others = sorted((k for k in ctx.reg.guides if k != key), key=lambda k: (k != "scams", k))
    if others:
        body.append(_section("More guides", '<ul class="inline">' + "".join(
            f'<li><a href="{r}{guide_path(k)}">{escape(str(ctx.reg.guides[k].meta.get("title") or k).split(" — ")[0])}</a></li>' for k in others) + "</ul>"))
    body.append(f'<p class="notes" style="margin-top:24px">Markdown: <a href="{r}guides/{escape(key)}.md">guides/{escape(key)}.md</a></p>')
    body.append(cta(ctx, ASK_DEFAULT.format(c="[company]")))
    short = _short_intro(g.body)
    return Page(
        path=path,
        title=_fit([f"{title} | {SITE_NAME}", title, f"{title.split(' — ')[0]} | {SITE_NAME}", title.split(" — ")[0]], TITLE_MAX),
        description=_fit([short or title], DESCRIPTION_MAX),
        crumbs=[(title.split(" — ")[0], path)],
        body="".join(body),
        lastmod=lv or None,
        json=f"guides/{key}.md",
    )


def _short_intro(body: str) -> str:
    """The first paragraph of the "In short" section, as plain text."""
    from .context import sections

    lines = sections(body).get("In short") or body.splitlines()
    para = " ".join(line.strip() for line in lines if line.strip() and not line.startswith(("#", "<!--")))
    para = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", para)
    return para.replace("**", "").replace("`", "")


# ---- shared pieces -----------------------------------------------------------


def _head(h1: str, meta: str | None) -> str:
    return f"<h1>{escape(h1)}</h1>" + (f'<p class="meta-line">{escape(meta)}</p>' if meta else "")


def _section(title: str, inner: str, anchor: str | None = None) -> str:
    attr = f' id="{escape(anchor)}"' if anchor else ""
    return f'<section class="section"{attr}><h2>{escape(title)}</h2>{inner}</section>'


def cred_line(cr: dict) -> str:
    pct = round((cr.get("primary_share") or 0) * 100)
    vf = cr.get("verified_from") or {}
    weak = vf.get("search_snippet", 0) + vf.get("archive", 0)
    dossier = f" · dossier {escape(cr['dossier_last_verified'])}" if cr.get("dossier_last_verified") else ""
    return (f'<div class="cred"><span class="grade grade-{escape(cr["grade"])}" title="Credibility grade">{escape(cr["grade"])}</span>'
            f'<span>Credibility {escape(cr["grade"])} · last verified <b>{escape(cr.get("last_verified") or "unknown")}</b>{dossier}'
            f' · {pct}% official or government sources{f" · {weak} from search snippets or archives" if weak else ""}</span>'
            f'<details><summary>What does this mean?</summary><p>{escape(cr.get("explanation") or "")}</p></details></div>')


def cta(ctx: _Ctx, prompt: str) -> str:
    return ('<section class="cta" aria-labelledby="cta-h"><h2 id="cta-h">Let your AI agent handle this</h2>'
            '<p>Escalate Anything is a free, open-source MCP server for Claude, Cursor, VS Code, Gemini CLI, Codex and other AI apps. '
            'Your agent gets this playbook, keeps a case log with reference numbers and follow-up dates, '
            'and drafts each message for you to approve.</p>'
            '<p class="label">1. Set it up (needs <a href="https://docs.astral.sh/uv/">uv</a>):</p>'
            '<pre class="code"><code>uvx escalate-anything setup</code></pre>'
            '<p class="label">2. Ask your agent:</p>'
            f'<pre class="code"><code>{escape(prompt)}</code></pre>'
            f'<p class="more"><a href="{escape(ctx.repo)}">Source code, other install options and the Claude Code plugin</a></p></section>')


def src_html(x: dict, today: dt.date) -> str:
    src = x.get("source")
    if not src:
        return ""
    lv = x.get("last_verified")
    link = f'<a href="{escape(src)}">Source: {escape(_host(src))}</a>' if _is_url(src) else f"Source: {escape(src)}"
    stale = ' <span class="badge warn">check source</span>' if x.get("stale") or _stale(lv, today) else ""
    return f'<p class="src">{link}{f", verified {escape(str(lv))}" if lv else ""}{stale}</p>'


def fact_html(f: dict, today: dt.date) -> str:
    kind = f'<span class="kind">{escape(FACT.get(f.get("kind"), _human(f["kind"])))}</span>' if f.get("kind") else ""
    return f'<li class="fact">{kind}<p>{escape(f["claim"])}</p>{src_html(f, today)}</li>'


def tip_html(t: dict, today: dt.date) -> str:
    who = "Community tip" if t.get("kind") == "community" else "Company tip"
    return f'<li class="fact"><span class="kind">{who}</span><p>{escape(t["text"])}</p>{src_html(t, today)}</li>'


def rule_html(r: dict, today: dt.date) -> str:
    title = f'<a class="rule-title" href="{escape(r["source"])}">{escape(r["title"])}</a>' if _is_url(r.get("source")) else f'<span class="rule-title">{escape(r["title"])}</span>'
    cite = f'<div class="cite">{escape(r["citation"])}</div>' if r.get("citation") else ""
    if r.get("do_not_cite"):
        note = f"<p>{escape(r['status_note'])}</p>" if r.get("status_note") else ""
        return (f'<li class="rule off">{title} <span class="badge bad">{escape(STATUS.get(r["status"], _human(r["status"])))}</span>'
                f"{cite}{note}<p class=\"src\">Not in force. Do not cite it as current law.</p></li>")
    partial = ' <span class="badge warn">Partly in effect</span>' if r.get("status") == "partially_in_effect" else ""
    pts = r.get("points") or []
    details = (f'<details><summary>{_plural(len(pts), "citable point")}</summary><ul class="facts">'
               + "".join(fact_html(p, today) for p in pts) + "</ul></details>") if pts else ""
    return f'<li class="rule">{title}{partial}{cite}<p>{escape(r.get("summary", ""))}</p>{src_html(r, today)}{details}</li>'


def value_html(ch: dict) -> str:
    v = str(ch.get("value", ""))
    t = ch.get("type")
    href = None
    if t == "phone":
        href = tel_href(v)
    elif t == "sms":
        href = "sms:" + re.sub(r"[^\d+]", "", v)
    elif t == "email":
        href = "mailto:" + v
    elif t not in ("fax", "mail", "in_person") and _is_url(v):
        href = v
    if href:
        return f'<a href="{escape(href)}">{escape(_short_url(v) if _is_url(v) else v)}</a>'
    return f'<span class="plain">{escape(v)}</span>'


def tel_href(v: str) -> str:
    num, *ext = re.split(r"\s*ext\.?\s*", v, maxsplit=1, flags=re.I)
    out = "tel:" + re.sub(r"[^\d+*#]", "", num).replace("#", "%23")
    digits = re.sub(r"\D", "", ext[0]) if ext else ""
    return out + ("," + digits if digits else "")


def _access(ch: dict) -> str:
    a = ACCESS.get(ch.get("access"))
    return f' <span class="badge{" " + a[1] if a[1] else ""}">{escape(a[0])}</span>' if a else ""


def channel_line(ch: dict) -> str:
    """One line for a channel inside a step or a ladder rung."""
    label = escape(ch.get("label", ""))
    main = f'<a href="{escape(ch["value"])}">{label}</a>' if _is_url(ch.get("value")) else f"<span>{label}</span> {value_html(ch)}"
    return f'<div class="step-ch"><span class="type">{escape(TYPE.get(ch.get("type"), _human(ch.get("type", ""))))}</span>{main}{_access(ch)}</div>'


def regulator_line(rg: dict) -> str:
    chans = rg.get("channels") or []
    form = next((c for c in chans if c.get("type") in ("web_form", "portal") and _is_url(c.get("value"))), None) \
        or next((c for c in chans if _is_url(c.get("value"))), None)
    phone = next((c for c in chans if c.get("type") == "phone"), None)
    name = f'<a href="{escape(form["value"])}">{escape(rg["name"])}</a>' if form else f"<span>{escape(rg['name'])}</span>"
    tel = f' <a href="{escape(tel_href(phone["value"]))}">{escape(phone["value"])}</a>' if phone else ""
    return f'<div class="step-ch"><span class="type">Regulator</span>{name}{tel}</div>'


def ladder_html(ctx: _Ctx, ladder: list[dict], channels: list[dict], sector: str, r: str) -> str:
    by_id = {ch["id"]: ch for ch in channels}
    items = []
    for step in ladder:
        detail = ""
        if step.get("channel"):
            detail = channel_line(step["channel"])
        elif step.get("candidate_channels"):
            detail = "".join(channel_line(by_id[i]) for i in step["candidate_channels"][:2] if i in by_id)
        if step.get("regulator"):
            detail = regulator_line(step["regulator"])
        if step["rung"] == "state_agency":
            kind = AGENCY.get(step.get("agency_kind") or "", "consumer protection agency")
            detail = (f'<p>Your state’s {escape(kind)}. Find it in the <a href="{r}#/states">list of state agencies</a> '
                      f'(also as JSON: <code>states/&lt;code&gt;.json</code>, for example <a href="{r}states/ny.json">states/ny.json</a>).</p>')
        if step["rung"] == "payment_dispute" and step.get("rules"):
            detail = "".join(f'<p><a href="{escape(ctx.reg.rules[i]["source"])}">{escape(ctx.reg.rules[i]["title"])}</a></p>'
                             for i in step["rules"] if i in ctx.reg.rules and _is_url(ctx.reg.rules[i].get("source")))
        note = f'<p class="rung-note">{escape(step["note"])}</p>' if step.get("note") else ""
        items.append(f'<li><p class="rung">{escape(RUNG.get(step["rung"], _human(step["rung"])))}</p>{detail}{note}</li>')
    out = f'<ol class="ladder">{"".join(items)}</ol>'
    kinds = ctx.reg.sectors.get(sector, {}).get("state_agency_kinds", [])
    if kinds and not any(step["rung"] == "state_agency" for step in ladder):
        # find_regulators(sector, state) returns these agencies for the person's state.
        names = " or ".join(AGENCY.get(k, _human(k).lower()) for k in kinds)
        out += (f'<p class="notes">State agencies for this sector: your state’s {escape(names)}. Find yours in the '
                f'<a href="{r}#/states">list of state agencies</a>, or as JSON in <code>states/&lt;code&gt;.json</code> '
                f'(for example <a href="{r}states/ny.json">states/ny.json</a>).</p>')
    return out


ORDER = ["phone", "sms", "chat", "web_form", "portal", "email", "app", "mail", "in_person", "social", "fax"]


def channel_html(ctx: _Ctx, ch: dict, r: str, company: str | None = None, playbooks: set[str] | None = None) -> str:
    uses = []
    for i in ch.get("purposes") or []:
        name = escape(ctx.issue_name(i))
        uses.append(f'<a href="{r}{playbook_path(company, i)}">{name}</a>' if company and playbooks and i in playbooks else name)
    return (f'<li class="ch"><div><span class="ch-label">{escape(ch.get("label", ""))}</span>{_access(ch)}</div>'
            f'<div class="ch-value">{value_html(ch)}</div>'
            + (f'<p class="ch-hours">Hours: {escape(ch["hours"])}</p>' if ch.get("hours") else "")
            + (f'<p class="ch-notes">{escape(ch["notes"])}</p>' if ch.get("notes") else "")
            + (f'<p class="ch-for">Use for: {", ".join(uses)}</p>' if uses else "")
            + src_html(ch, ctx.today) + "</li>")


def channel_groups(ctx: _Ctx, c: dict, r: str) -> str:
    groups: dict[str, list[dict]] = {}
    for ch in c.get("channels", []):
        groups.setdefault(ch.get("type", "other"), []).append(ch)
    types = [t for t in ORDER if t in groups] + [t for t in groups if t not in ORDER]
    playbooks = {p["issue"] for p in c.get("playbooks", [])}
    return "".join(f'<div class="ch-group box"><h3>{escape(GROUP.get(t, _human(t)))}</h3><ul class="ch-list">'
                   + "".join(channel_html(ctx, ch, r, c["id"], playbooks) for ch in groups[t]) + "</ul></div>" for t in types)


# ---- Markdown: ## to #### headings, "- " bullets, paragraphs, **bold**, `code`, [text](http(s) url) ----
# The same subset as renderMarkdown in web/app.js. Each block is HTML-escaped before markup is added;
# a link with another scheme renders as its text, and HTML comments are dropped.

_INLINE = re.compile(r"\[([^\]\n]+)\]\(([^)\s]+)\)|\*\*(.+?)\*\*|`([^`\n]+)`")


def _md_inline(escaped: str) -> str:
    def sub(m: re.Match) -> str:
        text, url, bold, code = m.groups()
        if bold is not None:
            return f"<strong>{_md_inline(bold)}</strong>"
        if code is not None:
            return f"<code>{code}</code>"
        inner = _md_inline(text)
        return f'<a href="{url}">{inner}</a>' if re.match(r"https?://", url, re.I) else inner

    return _INLINE.sub(sub, escaped)


def render_markdown(src: str, top: int = 2) -> str:
    """Markdown to HTML. `top` is the heading level for "##"."""
    out: list[str] = []
    para: list[str] = []
    items: list[str] | None = None
    comment = False

    def flush() -> None:
        nonlocal para, items
        if para:
            out.append(f"<p>{_md_inline(escape(' '.join(para), quote=True))}</p>")
            para = []
        if items is not None:
            out.append("<ul>" + "".join(f"<li>{_md_inline(escape(li, quote=True))}</li>" for li in items) + "</ul>")
            items = None

    for raw in (src or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        t = raw.strip()
        if comment:
            comment = "-->" not in t
            continue
        if t.startswith("<!--"):
            if para:
                out.append(f"<p>{_md_inline(escape(' '.join(para), quote=True))}</p>")
                para = []
            comment = "-->" not in t
            continue
        if not t:
            flush()
            continue
        m = re.match(r"^(#{1,4})\s+(.+)$", t)
        if m:
            flush()
            level = min(6, max(top, top + len(m.group(1)) - 2))
            text = re.sub(r"\s+#+$", "", m.group(2))
            out.append(f"<h{level}>{_md_inline(escape(text, quote=True))}</h{level}>")
            continue
        m = re.match(r"^-\s+(.*)$", t)
        if m:
            if para:
                out.append(f"<p>{_md_inline(escape(' '.join(para), quote=True))}</p>")
                para = []
            items = (items or []) + [m.group(1)]
            continue
        if items is not None:
            items[-1] += " " + t  # a wrapped bullet line
            continue
        para.append(t)
    flush()
    return "\n".join(out)


def doc_html(markdown: str, top: int) -> str:
    """A dossier or guide. "Reported by customers" at the start of a bullet becomes a badge."""
    return re.sub(r"<li>Reported by customers:?\s*",
                  '<li><span class="badge warn">Reported by customers</span> ', render_markdown(markdown, top))


# ---- the document ------------------------------------------------------------


def render(ctx: _Ctx, page: Page) -> str:
    r = _root(page.path)
    url = ctx.base + page.path
    crumbs = [(SITE_NAME, "")] + page.crumbs
    ld = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [{"@type": "ListItem", "position": n, "name": name, "item": ctx.base + p}
                            for n, (name, p) in enumerate(crumbs, 1)],
    }
    current = ' aria-current="page"'
    nav = "".join(f'<li><a href="{r}{p}"{current if i == len(crumbs) - 1 else ""}>{escape(name)}</a></li>'
                  for i, (name, p) in enumerate(crumbs))
    report = f"{ctx.repo}/issues/new?template=data-correction.yml" + (f"&company={quote(page.company)}" if page.company else "")
    title, desc = escape(page.title), escape(page.description)
    alt = f'\n<link rel="alternate" type="{"text/markdown" if page.json.endswith(".md") else "application/json"}" href="{r}{escape(page.json)}">' if page.json else ""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{escape(url)}">
<meta property="og:type" content="{page.og_type}">
<meta property="og:site_name" content="{SITE_NAME}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{escape(url)}">
<meta property="og:image" content="{escape(ctx.base)}og.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title}">
<meta name="twitter:description" content="{desc}">
<meta name="twitter:image" content="{escape(ctx.base)}og.png">
<meta name="color-scheme" content="light dark">
<link rel="stylesheet" href="{r}assets/pages.css">{alt}
<script type="application/ld+json">{_json_ld(ld)}</script>
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header class="topbar"><div class="wrap topbar-inner">
<a class="brand" href="{r}">{SITE_NAME}</a>
<nav class="nav" aria-label="Main"><a href="{r}">Companies</a><a href="{r}#/issues">Issues</a><a href="{r}#/states">States</a><a href="{r}guides/scams/">Scam guide</a><a href="{r}#/agents">For agents</a></nav>
</div></header>
<main id="main" class="wrap">
<nav class="crumbs" aria-label="Breadcrumb"><ol>{nav}</ol></nav>
{page.body}
</main>
<footer class="footer"><div class="wrap">
<p><strong>Wrong or outdated?</strong> <a href="{escape(report)}">Report it</a>. Contacts change: check the source before you rely on a value.</p>
<p>Not legal advice. <a href="{r}">{SITE_NAME}</a> is an open index of how to get problems resolved with large US companies. <a href="{escape(ctx.repo)}">Source and MCP server</a> · <a href="{r}llms.txt">llms.txt</a></p>
<p>Data from <a href="{escape(ctx.repo)}">Escalate Anything</a>, licensed <a href="{CC_BY}">CC BY 4.0</a>. Built {ctx.today.isoformat()}.</p>
</div></footer>
</body>
</html>
"""


def stylesheet() -> str:
    """The color tokens of the app's style.css, then pages.css."""
    app = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    marker = "\n*, *::before"
    if marker not in app:
        raise ValueError("web/style.css changed: the tokens must come before the '*, *::before' rule")
    return app.split(marker, 1)[0].rstrip() + "\n\n" + (WEB_DIR / "pages.css").read_text(encoding="utf-8")


def sitemap(entries: list[tuple[str, str | None]], base_url: str) -> str:
    rows = []
    for path, lastmod in entries:
        lm = f"<lastmod>{xml_escape(lastmod)}</lastmod>" if lastmod else ""
        rows.append(f"<url><loc>{xml_escape(base_url + path)}</loc>{lm}</url>")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "\n".join(rows) + "\n</urlset>\n")


# ---- helpers -----------------------------------------------------------------


def _root(path: str) -> str:
    return "../" * path.count("/")


def _json_ld(obj: Any) -> str:
    # "<" never appears in JSON outside strings, so this keeps </script> out of the block.
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")


def _fit(candidates: list[str], limit: int) -> str:
    """The first candidate that fits, else the first one cut at a word boundary."""
    candidates = [" ".join(c.split()) for c in candidates if c and c.strip()]
    for c in candidates:
        if len(c) <= limit:
            return c
    text = candidates[0] if candidates else ""
    cut = text[: limit - 1].rsplit(" ", 1)[0].rstrip(",;:.-–— ")
    return cut + "…"


def _newest(node: Any) -> str | None:
    """The newest last_verified date anywhere in node."""
    best: str | None = None
    stack = [node]
    while stack:
        n = stack.pop()
        if isinstance(n, dict):
            lv = n.get("last_verified")
            if isinstance(lv, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", lv) and (best is None or lv > best):
                best = lv
            stack.extend(n.values())
        elif isinstance(n, list):
            stack.extend(n)
    return best


def _plain(value: Any) -> str:
    """A YAML list item with an unquoted ': ' loads as {key: value}; show it as the text that was written."""
    if isinstance(value, dict):
        return "; ".join(f"{k}: {v}" for k, v in value.items())
    return str(value)


def _short_name(name: str) -> str:
    """'Microsoft (Microsoft 365 and Xbox Game Pass subscriptions)' -> 'Microsoft'."""
    return re.sub(r"\s*\([^)]*\)", "", name).strip() or name


def _lower_first(text: str) -> str:
    """'Delayed bag' -> 'delayed bag', but keep 'DOT' or 'HSA'."""
    return text[0].lower() + text[1:] if len(text) > 1 and text[1].islower() else text


def _human(text: str) -> str:
    return str(text).replace("_", " ").replace("-", " ").capitalize()


def _plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n:,} {one if n == 1 else many or one + 's'}"


def _is_url(v: Any) -> bool:
    return isinstance(v, str) and re.match(r"https?://", v, re.I) is not None


def _host(url: str) -> str:
    h = urlsplit(url).netloc.lower()
    return h[4:] if h.startswith("www.") else h


def _short_url(url: str) -> str:
    x = urlsplit(url)
    s = _host(url) + ("" if x.path in ("", "/") else x.path) + (f"?{x.query}" if x.query else "")
    return s if len(s) <= 58 else s[:42] + "…" + s[-14:]


def _stale(lv: Any, today: dt.date) -> bool:
    try:
        return (today - dt.date.fromisoformat(str(lv))).days > STALE_AFTER_DAYS
    except ValueError:
        return False
