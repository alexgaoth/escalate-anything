"""Build the static website: one self-contained page plus JSON files for people and agents.

Output (served by GitHub Pages):

    index.html              the directory (inline CSS and JS, index data embedded)
    registry.json           Registry.export()
    companies.json          one summary per company
    companies/<id>.json     company record, resolved playbooks and escalation ladder
    issues.json             issue vocabulary with the companies that have a playbook
    states/<code>.json      state agencies
    llms.txt                how an agent should use the data, with every company URL
    .nojekyll
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

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
    (out / "companies").mkdir(parents=True, exist_ok=True)
    (out / "states").mkdir(parents=True, exist_ok=True)

    _write_json(out / "registry.json", reg.export())

    companies = sorted(reg.companies.values(), key=lambda c: c["name"].lower())
    for c in companies:
        _write_json(out / "companies" / f"{c['id']}.json", company_document(reg, c, base_url, today))
    _write_json(out / "companies.json", [company_summary(reg, c) for c in companies])

    _write_json(out / "issues.json", issues_document(reg))
    for code, st in sorted(reg.states.items()):
        _write_json(out / "states" / f"{code}.json", st)

    (out / "llms.txt").write_text(llms_txt(reg, base_url), encoding="utf-8")
    (out / "index.html").write_text(index_html(reg, base_url, today), encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    return {"companies": len(companies), "states": len(reg.states), "issues": len(reg.issues)}


# ---- JSON documents ----------------------------------------------------------


def company_document(reg: Registry, c: dict, base_url: str = BASE_URL, today: dt.date | None = None) -> dict:
    """The company record plus every playbook resolved by get_playbook (no state)."""
    today = today or dt.date.today()
    return {
        "id": c["id"],
        "page": f"{base_url}#/c/{c['id']}",
        "generated": today.isoformat(),
        "company": c,
        "playbooks": {pb["issue"]: get_playbook(reg, c["id"], pb["issue"], None, today) for pb in c.get("playbooks", [])},
        "escalation": get_escalation(reg, c["id"], None, today)["ladder"],
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
        "playbook per issue with steps, channels, evidence, facts, rules and the escalation ladder.",
        "2. If the company is not listed, use the generic steps for the issue in issues.json and the regulators in registry.json.",
        "3. Cite only facts and rule points that have a `source`, and give that source URL. Do not cite a rule whose "
        "status is not in_effect or partially_in_effect.",
        "4. The person approves every message and form submission before it is sent. Draft; do not send on your own.",
        "5. Never enter passwords or payment details. A channel with access `login`, `captcha` or `human_only` needs the person.",
        "6. On a call or chat, say that you are an AI assistant acting for the person.",
        f"7. This is not legal advice. Contacts change: if a value is wrong, report it at {REPO_URL}/issues.",
        "",
        "## Data",
        "",
        f"- [Company index]({base_url}companies.json): id, name, aliases, sector and playbook issues for every company",
        f"- [Issues]({base_url}issues.json): issue vocabulary, generic steps, evidence, and the companies with a playbook",
        f"- [Whole registry]({base_url}registry.json): sectors, issues, regulators, states, rules and companies in one file",
        f"- [MCP server and skills]({REPO_URL}): `redress serve` adds a case log, draft briefs and bill tracking",
        "",
        "## Companies",
        "",
    ]
    for c in sorted(reg.companies.values(), key=lambda c: c["name"].lower()):
        issues = ", ".join(pb["issue"] for pb in c.get("playbooks", [])) or "no playbooks yet"
        lines.append(f"- [{c['name']}]({base_url}companies/{c['id']}.json): {sector_names.get(c['sector'], c['sector'])}; playbooks: {issues}")
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
