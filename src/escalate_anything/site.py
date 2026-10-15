"""Build the static website: one self-contained page plus JSON files for people and agents.

Output (served by GitHub Pages):

    index.html              the directory (inline CSS and JS, index data embedded)
    registry.json           Registry.export()
    companies.json          one summary per company
    companies/<id>.json     company record, resolved playbooks, escalation ladder, scam warnings and dossier
    issues.json             issue vocabulary with the companies that have a playbook
    states/<code>.json      state agencies
    dossiers/<id>.md        company dossiers ("how it actually goes"), copied from the registry
    guides/<key>.md         sector guides and the scam guide, copied from the registry
    llms.txt                how an agent should use the data, with every company URL
    .nojekyll

and the static, indexable HTML pages from pages.py:

    c/<id>/                 company page
    c/<id>/<issue-slug>/    one page per playbook (issue id with "_" changed to "-")
    issues/<issue-slug>/    issue hub with every company playbook for the issue
    guides/<key>/           guide rendered from Markdown
    assets/pages.css, sitemap.xml, robots.txt
"""

from __future__ import annotations

import datetime as dt
import json
import shutil
from pathlib import Path
from typing import Any

from . import context
from .credibility import company_credibility
from .advisor import company_summary, get_escalation, get_playbook
from .pages import build_pages, company_path, guide_path, issue_path, playbook_path
from .registry import Registry

BASE_URL = "https://escalate.alexgaoth.com/"
REPO_URL = "https://github.com/alexgaoth/escalate-anything"
WEB_DIR = Path(__file__).with_name("web")


def build_site(out_dir: Path, reg: Registry, base_url: str = BASE_URL, today: dt.date | None = None) -> dict[str, int]:
    """Write the site into out_dir. Returns counts of what was written."""
    today = today or dt.date.today()
    base_url = base_url if base_url.endswith("/") else base_url + "/"
    out = Path(out_dir)
    for sub in ("companies", "states", "dossiers", "guides"):
        (out / sub).mkdir(parents=True, exist_ok=True)

    _write_json(out / "registry.json", reg.export())

    companies = sorted(reg.companies.values(), key=lambda c: c["name"].lower())
    company_docs = {c["id"]: company_document(reg, c, base_url, today) for c in companies}
    for cid, doc in company_docs.items():
        _write_json(out / "companies" / f"{cid}.json", doc)
    _write_json(out / "companies.json", [company_summary(reg, c) for c in companies])

    _write_json(out / "issues.json", issues_document(reg))
    for code, st in sorted(reg.states.items()):
        _write_json(out / "states" / f"{code}.json", st)

    for sub, docs in (("dossiers", reg.dossiers), ("guides", reg.guides)):
        for key, doc in sorted(docs.items()):
            (out / sub / f"{key}.md").write_text(doc.path.read_text(encoding="utf-8"), encoding="utf-8")

    (out / "llms.txt").write_text(llms_txt(reg, base_url), encoding="utf-8")
    if (WEB_DIR / "og.png").exists():
        shutil.copyfile(WEB_DIR / "og.png", out / "og.png")
    (out / "badges").mkdir(exist_ok=True)
    for name, data in badges(reg, today).items():
        _write_json(out / "badges" / f"{name}.json", data)
    (out / "index.html").write_text(index_html(reg, base_url, today), encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    pages = build_pages(out, reg, company_docs, base_url, REPO_URL, today)
    return {"companies": len(companies), "states": len(reg.states), "issues": len(reg.issues),
            "dossiers": len(reg.dossiers), "guides": len(reg.guides), **pages}


# ---- JSON documents ----------------------------------------------------------


def company_document(reg: Registry, c: dict, base_url: str = BASE_URL, today: dt.date | None = None) -> dict:
    """The company record, every playbook resolved by get_playbook (no state), scam warnings and the dossier."""
    today = today or dt.date.today()
    dossier = reg.dossiers.get(c["id"])
    guide = reg.guides.get(c["sector"])
    return {
        "id": c["id"],
        "page": f"{base_url}#/c/{c['id']}",
        "html": base_url + company_path(c["id"]),
        "generated": today.isoformat(),
        "company": c,
        "playbooks": {pb["issue"]: get_playbook(reg, c["id"], pb["issue"], None, today) for pb in c.get("playbooks", [])},
        "escalation": get_escalation(reg, c["id"], None, today)["ladder"],
        "security": context.security_view(c),
        "credibility": company_credibility(reg, c, today),
        "dossier": {**_doc_meta(dossier), "file": f"dossiers/{c['id']}.md", "markdown": dossier.body} if dossier else None,
        "guide": {"key": c["sector"], **_doc_meta(guide), "file": f"guides/{c['sector']}.md",
                  "page": f"{base_url}#/guides/{c['sector']}"} if guide else None,
    }


def _card_credibility(reg: Registry, c: dict, today: dt.date) -> dict[str, str]:
    cc = company_credibility(reg, c, today)
    return {"grade": cc["grade"], "verified": cc["last_verified"] or ""}


def _doc_meta(doc: context.Doc | None) -> dict[str, str]:
    meta = doc.meta if doc else {}
    return {"title": str(meta.get("title") or ""), "last_verified": str(meta.get("last_verified") or "")}


def issues_document(reg: Registry) -> list[dict]:
    with_playbook = _companies_by_issue(reg)
    return [{**i, "companies": with_playbook.get(iid, [])} for iid, i in reg.issues.items()]


def _companies_by_issue(reg: Registry) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for c in sorted(reg.companies.values(), key=lambda c: c["name"].lower()):
        for pb in c.get("playbooks", []):
            out.setdefault(pb["issue"], []).append(c["id"])
    return out


def index_data(reg: Registry, base_url: str, today: dt.date) -> dict[str, Any]:
    """The small index the page embeds. Details are fetched from companies/<id>.json."""
    stats = reg.stats()
    counts: dict[str, int] = {}
    for c in reg.companies.values():
        counts[c["sector"]] = counts.get(c["sector"], 0) + 1
    with_playbook = _companies_by_issue(reg)
    return {
        "generated": today.isoformat(),
        "base": base_url,
        "repo": REPO_URL,
        "stats": {k: stats[k] for k in ("companies", "playbooks", "channels", "regulators", "states", "rules", "issues")},
        "sectors": [{"id": s["id"], "name": s["name"], "count": counts.get(s["id"], 0)} for s in reg.sectors.values()],
        "issues": [
            {
                "id": i["id"],
                "name": i["name"],
                "description": i.get("description", ""),
                "sectors": i.get("sectors", []),
                "evidence": i.get("evidence", []),
                "steps": i.get("steps", []),
                "companies": with_playbook.get(i["id"], []),
            }
            for i in reg.issues.values()
        ],
        "companies": [
            {
                "id": c["id"],
                "name": c["name"],
                "aliases": c.get("aliases", []),
                "sector": c["sector"],
                "also": c.get("also_sectors", []),
                "channels": len(c.get("channels", [])),
                "issues": [pb["issue"] for pb in c.get("playbooks", [])],
                **_card_credibility(reg, c, today),
            }
            for c in sorted(reg.companies.values(), key=lambda c: c["name"].lower())
        ],
        "states": [
            {
                "id": st["id"],
                "name": st["name"],
                "agencies": [
                    {"kind": ag["kind"], "name": ag["name"], "website": ag.get("website"), "sectors": ag.get("covers_sectors", [])}
                    for ag in st.get("agencies", [])
                ],
            }
            for st in sorted(reg.states.values(), key=lambda s: s["name"])
        ],
        "rules": {
            rid: {"title": r["title"], "status": r["status"], "source": r["source"], "citation": r.get("citation")}
            for rid, r in reg.rules.items()
        },
        "regulators": dict(reg.regulator_names),
        # The scam guide first, then the sector guides by title.
        "guides": [
            {"key": key, **_doc_meta(doc), "sector": doc.meta.get("sector"), "topic": doc.meta.get("topic")}
            for key, doc in sorted(reg.guides.items(), key=lambda kv: (kv[0] != "scams", _doc_meta(kv[1])["title"].lower()))
        ],
        "dossiers": sorted(reg.dossiers),
    }


# ---- llms.txt ----------------------------------------------------------------


def badges(reg: Registry, today: dt.date | None = None) -> dict[str, dict]:
    """shields.io endpoint badges, so the README shows live counts: img.shields.io/endpoint?url=<site>/badges/<name>.json"""
    from .credibility import registry_credibility

    st = reg.stats()
    cred = registry_credibility(reg, today)
    def badge(label: str, message: str, color: str) -> dict:
        return {"schemaVersion": 1, "label": label, "message": message, "color": color}
    return {
        "companies": badge("companies", str(st["companies"]), "2ea44f"),
        "contacts": badge("verified contacts", f"{st['channels']:,}", "2ea44f"),
        "verified": badge("data verified", cred["last_verified"] or "unknown", "0969da"),
        "dossiers": badge("dossiers", str(st.get("dossiers", 0)), "8250df"),
        "credibility": badge("grade A", f"{cred['grades']['A']} of {st['companies']}", "1a7f37"),
    }


def llms_txt(reg: Registry, base_url: str = BASE_URL) -> str:
    stats = reg.stats()
    sector_names = {sid: s["name"] for sid, s in reg.sectors.items()}
    lines = [
        "# Escalate Anything",
        "",
        "> An open index of how to get problems resolved with large US companies: contact channels with deep links, "
        "playbooks per issue, escalation ladders, sourced facts, federal regulators, state agencies and consumer-protection "
        f"rules. It covers {stats['companies']} companies, {stats['playbooks']} playbooks and all 50 states and DC. "
        "Every value has a source URL and a last_verified date.",
        "",
        "How an agent should use it:",
        "",
        f"1. Find the company in the list below and fetch its JSON, for example {base_url}companies/united-airlines.json. "
        "It has the company record (channels, escalation, facts, tips, known_blockers) and `playbooks`: one resolved "
        "playbook per issue with steps, channels, evidence, facts, rules and the escalation ladder. It also has "
        "`security` (official domains, what the company never asks for, known scams, where to report phishing), "
        "`dossier` (how complaints actually go, as Markdown with a source on every bullet) and `guide` (the sector guide).",
        "2. If the company is not listed, use the generic steps for the issue in issues.json and the regulators in registry.json.",
        "3. Use the phone numbers, URLs and email addresses in the company's JSON, not ones from a search result or a "
        "message. A message that asks for money, codes or account access can be a scam: compare it with the "
        "company's `security` field (what the company never asks for, and its known scams).",
        "4. Cite only facts and rule points that have a `source`, and give that source URL. Do not cite a rule whose "
        "status is not in_effect or partially_in_effect. In dossiers and guides, 'Reported by customers' marks an "
        "anecdote from a forum: a tactic to try, not a fact to quote to the company.",
        "5. The person approves every message and form submission before it is sent. Draft; do not send on your own.",
        "6. Never enter passwords or payment details. A channel with access `login`, `captcha` or `human_only` needs the person.",
        "7. On a call or chat, say that you are an AI assistant acting for the person.",
        f"8. This is not legal advice. Contacts change: if a value is wrong, report it at {REPO_URL}/issues.",
        "",
        "## Data",
        "",
        f"- [Company index]({base_url}companies.json): id, name, aliases, sector and playbook issues for every company",
        f"- [Issues]({base_url}issues.json): issue vocabulary, generic steps, evidence, and the companies with a playbook",
        f"- [Whole registry]({base_url}registry.json): sectors, issues, regulators, states, rules and companies in one file",
        f"- [MCP server and skills]({REPO_URL}): `escalate serve` adds a case log, draft briefs and bill tracking",
        f"- [Sitemap]({base_url}sitemap.xml): every HTML page. Each company, playbook, issue and guide has a plain HTML "
        f"page to cite or show a person: {base_url}c/<company-id>/, {base_url}c/<company-id>/<issue-slug>/ "
        f"(the issue id with `_` changed to `-`, for example {base_url}{playbook_path('united-airlines', 'delayed_baggage')}), "
        f"{base_url}issues/<issue-slug>/ and {base_url}guides/<key>/",
        "",
    ]
    if reg.guides:
        lines += ["## Guides", "", "Markdown. Every bullet cites its source.", ""]
        for key, doc in sorted(reg.guides.items(), key=lambda kv: (kv[0] != "scams", kv[0])):
            title = _doc_meta(doc)["title"] or key
            lines.append(f"- [{title}]({base_url}guides/{key}.md) ([HTML]({base_url}{guide_path(key)}))")
        lines.append("")
    by_issue = _companies_by_issue(reg)
    lines += ["## Issues", "", "HTML pages with the generic steps and every company playbook for the issue.", ""]
    for iid, i in reg.issues.items():
        n = len(by_issue.get(iid, []))
        lines.append(f"- [{i['name']}]({base_url}{issue_path(iid)}): `{iid}`, {n} company playbook{'' if n == 1 else 's'}")
    lines.append("")
    lines += ["## Companies", ""]
    if reg.dossiers:
        lines += ["A company with a dossier (how complaints actually go, Markdown) has a `dossier` link.", ""]
    for c in sorted(reg.companies.values(), key=lambda c: c["name"].lower()):
        issues = ", ".join(pb["issue"] for pb in c.get("playbooks", [])) or "no playbooks yet"
        dossier = f"; [dossier]({base_url}dossiers/{c['id']}.md)" if c["id"] in reg.dossiers else ""
        lines.append(f"- [{c['name']}]({base_url}companies/{c['id']}.json): {sector_names.get(c['sector'], c['sector'])}; "
                     f"playbooks: {issues}{dossier}; [HTML]({base_url}{company_path(c['id'])})")
    lines += ["", "## States", ""]
    for code, st in sorted(reg.states.items(), key=lambda kv: kv[1]["name"]):
        kinds = ", ".join(sorted({ag["kind"] for ag in st.get("agencies", [])}))
        lines.append(f"- [{st['name']}]({base_url}states/{code}.json): {kinds}")
    lines += ["", "## Optional", "", f"- [Website]({base_url}): the same data for people, searchable", ""]
    return "\n".join(lines)


# ---- index.html --------------------------------------------------------------


def index_html(reg: Registry, base_url: str = BASE_URL, today: dt.date | None = None) -> str:
    today = today or dt.date.today()
    data = index_data(reg, base_url, today)
    # "<" never appears in JSON outside strings, so this escape keeps </script> out of the blob.
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    noscript = "\n".join(
        f'<li><a href="{company_path(c["id"])}">{_html(c["name"])}</a></li>' for c in data["companies"]
    )
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    # Template tokens first, then the inlined assets, then the data, so no inserted text is rewritten.
    replacements = {
        "__COMPANIES__": str(data["stats"]["companies"]),
        "__BASE__": _html(base_url),
        "__REPO__": _html(REPO_URL),
        "__GENERATED__": today.isoformat(),
        "/*__CSS__*/": (WEB_DIR / "style.css").read_text(encoding="utf-8"),
        "/*__JS__*/": (WEB_DIR / "app.js").read_text(encoding="utf-8"),
        "__NOSCRIPT__": noscript,
        "__DATA__": blob,
    }
    for key, value in replacements.items():
        html = html.replace(key, value, 1) if key in ("__NOSCRIPT__", "__DATA__") else html.replace(key, value)
    return html


# ---- helpers -----------------------------------------------------------------


def _html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
