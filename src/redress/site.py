"""Build the static website: one self-contained page plus JSON files for people and agents.

Output (served by GitHub Pages):

    index.html              the directory (inline CSS and JS, index data embedded)
    registry.json           Registry.export()
    companies.json          one summary per company
    companies/<id>.json     company record, resolved playbooks, escalation ladder, scam warnings and dossier
    issues.json             issue vocabulary with the companies that have a playbook
    states/<code>.json      state agencies
    contacts.json           every phone number, URL and email on file, normalized, with its owner
    red_flags.json          the scam_check patterns, contact patterns and next steps
    dossiers/<id>.md        company dossiers ("how it actually goes"), copied from the registry
    guides/<key>.md         sector guides and the scam guide, copied from the registry
    llms.txt                how an agent should use the data, with every company URL
    .nojekyll

contacts.json and red_flags.json are generated from context.py, so the page's JavaScript checks give
the same verdicts as the verify_contact and scam_check tools.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from . import context
from .advisor import company_summary, get_escalation, get_playbook
from .registry import Registry

BASE_URL = "https://alexgaoth.github.io/redress/"
REPO_URL = "https://github.com/alexgaoth/redress"
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
    for c in companies:
        _write_json(out / "companies" / f"{c['id']}.json", company_document(reg, c, base_url, today))
    _write_json(out / "companies.json", [company_summary(reg, c) for c in companies])

    _write_json(out / "issues.json", issues_document(reg))
    for code, st in sorted(reg.states.items()):
        _write_json(out / "states" / f"{code}.json", st)

    _write_json(out / "contacts.json", contacts_document(reg, today))
    _write_json(out / "red_flags.json", red_flags_document(reg))
    for sub, docs in (("dossiers", reg.dossiers), ("guides", reg.guides)):
        for key, doc in sorted(docs.items()):
            (out / sub / f"{key}.md").write_text(doc.path.read_text(encoding="utf-8"), encoding="utf-8")

    (out / "llms.txt").write_text(llms_txt(reg, base_url), encoding="utf-8")
    (out / "index.html").write_text(index_html(reg, base_url, today), encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    return {"companies": len(companies), "states": len(reg.states), "issues": len(reg.issues),
            "dossiers": len(reg.dossiers), "guides": len(reg.guides)}


# ---- JSON documents ----------------------------------------------------------


def company_document(reg: Registry, c: dict, base_url: str = BASE_URL, today: dt.date | None = None) -> dict:
    """The company record, every playbook resolved by get_playbook (no state), scam warnings and the dossier."""
    today = today or dt.date.today()
    dossier = reg.dossiers.get(c["id"])
    guide = reg.guides.get(c["sector"])
    return {
        "id": c["id"],
        "page": f"{base_url}#/c/{c['id']}",
        "generated": today.isoformat(),
        "company": c,
        "playbooks": {pb["issue"]: get_playbook(reg, c["id"], pb["issue"], None, today) for pb in c.get("playbooks", [])},
        "escalation": get_escalation(reg, c["id"], None, today)["ladder"],
        "security": context.security_view(c),
        "dossier": {**_doc_meta(dossier), "file": f"dossiers/{c['id']}.md", "markdown": dossier.body} if dossier else None,
        "guide": {"key": c["sector"], **_doc_meta(guide), "file": f"guides/{c['sector']}.md",
                  "page": f"{base_url}#/guides/{c['sector']}"} if guide else None,
    }


def _doc_meta(doc: context.Doc | None) -> dict[str, str]:
    meta = doc.meta if doc else {}
    return {"title": str(meta.get("title") or ""), "last_verified": str(meta.get("last_verified") or "")}


def contacts_document(reg: Registry, today: dt.date | None = None) -> dict:
    """Every contact that verify_contact can match, keyed by its normalized value, in the order verify_contact checks them."""
    today = today or dt.date.today()
    owners: list[dict] = []
    phones: dict[str, list[dict]] = {}
    urls: dict[str, list[dict]] = {}
    emails: dict[str, list[dict]] = {}
    brands = context.brand_index(reg)
    for kind, oid, name, website, official, channels in context._owner_entries(reg):
        owners.append({"kind": kind, "id": oid, "name": name, "website": website,
                       "domains": sorted(context._domains(website, official))})
        for ch in channels:
            entry = {"owner": oid, "name": name, "kind": kind, "channel": ch.get("id"), "type": ch.get("type"),
                     "label": ch.get("label"), "source": ch.get("source"), "last_verified": ch.get("last_verified")}
            value = str(ch.get("value", ""))
            if ch.get("type") in context.PHONE_CHANNEL_TYPES and (phone := context.norm_phone(value)):
                phones.setdefault(phone, []).append(entry)
            elif ch.get("type") in context.URL_CHANNEL_TYPES and (url := context.norm_url(value)):
                urls.setdefault(url[0], []).append({"path": url[1], **entry})
            elif ch.get("type") == "email":
                emails.setdefault(value.strip().lower(), []).append(entry)
    return {
        "about": "Contacts on file in the redress registry. Before anyone calls, texts, emails or opens a contact, "
                 "normalize it and look it up here. If it is not here, or it belongs to a different organization, "
                 "do not use it. Use a contact from the company's own file instead.",
        "generated": today.isoformat(),
        "normalize": {
            "phone": "Keep the digits only. Remove a leading 1 from an 11-digit number. The result must have 10 digits, "
                     "or 3 to 6 digits (a short code). Look it up in `phones`.",
            "url": "Add https:// if there is no scheme. Host: lower case, with no user, port or leading 'www.'. "
                   "Path: lower case, with no query, fragment or trailing '/'. Look up the host in `urls`. An entry "
                   "matches if its path is empty, is equal to the path, or is a parent of the path.",
            "email": "The full address, trimmed and in lower case. Look it up in `emails`.",
            "domains": "An email address or URL whose host is one of an owner's `domains`, or a subdomain of one, "
                       "belongs to that owner even if the exact address is not on file.",
            "lookalike": "Split the host into segments on '.' and '-'. A brand token matches when a segment equals it, "
                         "a segment equals an affix from `brands.affixes` plus the token (or the token plus an affix), "
                         "or two adjacent segments join to it. A host that is not in `brands.known_hosts` and not under "
                         "any owner's `domains` imitates the company of the longest matching token. A company's "
                         "official domains are its `domains` in `owners`.",
        },
        "owners": owners,
        "brands": {
            "tokens": [list(t) for t in brands.tokens],
            "affixes": list(context.BRAND_AFFIXES),
            "stopwords": sorted(context.BRAND_STOPWORDS),
            "known_hosts": sorted(brands.known_hosts),
        },
        "aliases": list(reg._alias_index.items()),
        "phones": phones,
        "urls": urls,
        "emails": emails,
    }


def red_flags_document(reg: Registry) -> dict:
    """The scam_check patterns. The next steps and the note come from scam_check itself."""
    flagged = context.scam_check(reg, "pay with a gift card")
    calm = context.scam_check(reg, "")
    if flagged["risk"] == "low" or calm["risk"] != "low":
        raise RuntimeError("scam_check probe texts no longer give the expected risk levels")
    return {
        "about": "Red flags that scam_check looks for in a message. Search the message in lower case. The patterns "
                 "are case-insensitive and '.' also matches a line break. A match is a warning sign, not proof.",
        "flags": [{"id": fid, "pattern": pattern, "why": why} for fid, pattern, why in context.RED_FLAGS],
        "lookalike": {
            "flag": "lookalike_domain",
            "about": "Added after the pattern flags, once for each company that a URL or email domain in the message "
                     "imitates (see `normalize.lookalike` in contacts.json). The contact's verdict is then `lookalike`.",
            "why": context.LOOKALIKE_WHY,
            "advice": context.LOOKALIKE_ADVICE,
        },
        "suspicious_verdicts": list(context.SUSPICIOUS_VERDICTS),
        "contact_patterns": dict(context.CONTACT_PATTERNS),
        "risk": "high: a red flag and a suspicious contact (a verdict in `suspicious_verdicts`), or two or more red "
                "flags. medium: one red flag, or one suspicious contact. low: no red flag and no suspicious contact.",
        "next_steps": flagged["next_steps"],
        "next_steps_low": calm["next_steps"],
        "note": flagged["note"],
    }


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


def llms_txt(reg: Registry, base_url: str = BASE_URL) -> str:
    stats = reg.stats()
    sector_names = {sid: s["name"] for sid, s in reg.sectors.items()}
    lines = [
        "# redress",
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
        f"3. Verify every contact before you use it. Before anyone calls, texts, emails or opens a phone number, email "
        f"address or URL (also one that the person got in a message, or one you found in a search), look it up in "
        f"{base_url}contacts.json. Its `normalize` field tells how to normalize the value. If the value is not there, "
        "or it is on file for a different organization, do not use it. Use a contact from the company's JSON instead. "
        f"To check a whole message, apply the patterns in {base_url}red_flags.json.",
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
        f"- [Contacts on file]({base_url}contacts.json): every phone number, URL and email address in the registry, "
        "normalized, with its owner (company, regulator or state agency), label and source, plus each owner's official domains",
        f"- [Scam red flags]({base_url}red_flags.json): the patterns that mark a message as a likely scam, with the reason for each",
        f"- [Issues]({base_url}issues.json): issue vocabulary, generic steps, evidence, and the companies with a playbook",
        f"- [Whole registry]({base_url}registry.json): sectors, issues, regulators, states, rules and companies in one file",
        f"- [MCP server and skills]({REPO_URL}): `redress serve` adds a case log, draft briefs and bill tracking",
        "",
    ]
    if reg.guides:
        lines += ["## Guides", "", "Markdown. Every bullet cites its source.", ""]
        for key, doc in sorted(reg.guides.items(), key=lambda kv: (kv[0] != "scams", kv[0])):
            title = _doc_meta(doc)["title"] or key
            lines.append(f"- [{title}]({base_url}guides/{key}.md)")
        lines.append("")
    lines += ["## Companies", ""]
    if reg.dossiers:
        lines += ["A company with a dossier (how complaints actually go, Markdown) has a `dossier` link.", ""]
    for c in sorted(reg.companies.values(), key=lambda c: c["name"].lower()):
        issues = ", ".join(pb["issue"] for pb in c.get("playbooks", [])) or "no playbooks yet"
        dossier = f"; [dossier]({base_url}dossiers/{c['id']}.md)" if c["id"] in reg.dossiers else ""
        lines.append(f"- [{c['name']}]({base_url}companies/{c['id']}.json): {sector_names.get(c['sector'], c['sector'])}; playbooks: {issues}{dossier}")
    lines += ["", "## States", ""]
    for code, st in sorted(reg.states.items(), key=lambda kv: kv[1]["name"]):
        kinds = ", ".join(sorted({ag["kind"] for ag in st.get("agencies", [])}))
        lines.append(f"- [{st['name']}]({base_url}states/{code}.json): {kinds}")
    lines += ["", "## Optional", "", f"- [Website]({base_url}): the same data for people, searchable",
              f"- [Check before you call]({base_url}#/check): the contact and message checks, for people", ""]
    return "\n".join(lines)


# ---- index.html --------------------------------------------------------------


def index_html(reg: Registry, base_url: str = BASE_URL, today: dt.date | None = None) -> str:
    today = today or dt.date.today()
    data = index_data(reg, base_url, today)
    # "<" never appears in JSON outside strings, so this escape keeps </script> out of the blob.
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    noscript = "\n".join(
        f'<li><a href="companies/{c["id"]}.json">{_html(c["name"])}</a></li>' for c in data["companies"]
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
