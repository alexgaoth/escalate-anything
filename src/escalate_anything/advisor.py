"""Resolve playbooks, escalation ladders, regulators and rules from the registry.

Every function returns plain dicts, so the MCP layer and the CLI can share them.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from .registry import Registry

IN_FORCE = {"in_effect", "partially_in_effect"}
STALE_AFTER_DAYS = 365
GENERIC_PAYMENT_RULES = ["fcba-billing-error", "efta-reg-e"]

TONE_RULES = [
    "State facts, dates, amounts and reference numbers. Leave out adjectives and accusations.",
    "Cite only facts and rules that Escalate Anything returned, with their source URL. Never cite a rule whose status is not in force.",
    "Do not say 'fraud', 'illegal' or 'lawsuit' unless the person decided to, and a returned rule supports it.",
    "Make one clear request: the remedy, the amount, and a reasonable date for a reply (for example 14 days).",
    "Name the next step factually (for example, a complaint to the regulator) only if the person will take it.",
    "Keep it under 250 words. Polite and firm. Written by the person, in the first person.",
]


class NotFound(LookupError):
    pass


def resolve_company(reg: Registry, company: str) -> dict:
    if company in reg.companies:
        return reg.companies[company]
    hits = reg.find_company(company, limit=3)
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise NotFound(f"No company matches '{company}'. Use find_company, or treat it as an unlisted company and use the generic playbook with list_issues.")
    names = ", ".join(f"{h['id']} ({h['name']})" for h in hits)
    raise NotFound(f"'{company}' is ambiguous: {names}. Pass one of these ids.")


def company_summary(reg: Registry, c: dict) -> dict:
    from .credibility import company_credibility

    issues = [pb["issue"] for pb in c.get("playbooks", [])]
    cred = company_credibility(reg, c)
    return {
        "credibility": cred["grade"],
        "last_verified": cred["last_verified"],
        "id": c["id"],
        "name": c["name"],
        "sector": c["sector"],
        "also_sectors": c.get("also_sectors", []),
        "aliases": c.get("aliases", []),
        "website": c["website"],
        "playbook_issues": issues,
        "channel_count": len(c.get("channels", [])),
    }


def sector_issues(reg: Registry, sector: str | None) -> list[dict]:
    out = []
    for i in reg.issues.values():
        if sector is None or "all" in i["sectors"] or sector in i["sectors"]:
            out.append({"id": i["id"], "name": i["name"], "description": i["description"], "sectors": i["sectors"]})
    return out


# ---- freshness ---------------------------------------------------------------


def _age_days(item: dict, today: dt.date) -> int | None:
    try:
        return (today - dt.date.fromisoformat(item["last_verified"])).days
    except (KeyError, TypeError, ValueError):
        return None


def _mark(item: dict, today: dt.date, warnings: list[str], label: str) -> dict:
    out = dict(item)
    age = _age_days(item, today)
    if age is not None and age > STALE_AFTER_DAYS:
        out["stale"] = True
        warnings.append(f"{label} was last verified {item['last_verified']}; check the source before relying on it.")
    return out


# ---- regulators and state agencies ------------------------------------------


def _regulator_view(reg: Registry, rid: str, today: dt.date, warnings: list[str]) -> dict:
    r = reg.regulators.get(rid)
    if not r:
        return {"id": rid, "name": reg.regulator_names.get(rid, rid), "missing": "No detail file yet. Search the agency's official .gov site."}
    return {
        "id": rid,
        "name": r["name"],
        "level": r["level"],
        "when_to_use": r["when_to_use"],
        "channels": [_mark(ch, today, warnings, f"{rid} channel '{ch['id']}'") for ch in r["channels"]],
        "facts": [_mark(f, today, warnings, f"{rid} fact") for f in r.get("facts", [])],
        "notes": r.get("notes"),
    }


# Some states handle consumer protection outside the attorney general (Hawaii: DCCA).
KIND_FALLBACK = {"attorney_general": "consumer_affairs"}


def state_agencies(reg: Registry, state: str, sector: str, kind: str | None = None) -> list[dict]:
    st = reg.states.get(state.lower())
    if not st:
        return []

    def matching(k: str | None) -> list[dict]:
        out = []
        for ag in st["agencies"]:
            if k and ag["kind"] != k:
                continue
            covers = ag.get("covers_sectors")
            if covers and sector not in covers:
                continue
            out.append(ag)
        return out

    found = matching(kind)
    if not found and kind in KIND_FALLBACK:
        found = matching(KIND_FALLBACK[kind])
    return found


def find_regulators(reg: Registry, sector: str, state: str | None = None, today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    if sector not in reg.sectors:
        raise NotFound(f"Unknown sector '{sector}'. Known: {', '.join(reg.sectors)}")
    s = reg.sectors[sector]
    warnings: list[str] = []
    result: dict[str, Any] = {
        "sector": sector,
        "federal": [_regulator_view(reg, rid, today, warnings) for rid in s.get("federal_regulators", [])],
    }
    if state:
        kinds = s.get("state_agency_kinds", [])
        agencies = [ag for k in kinds for ag in state_agencies(reg, state, sector, k)]
        result["state"] = agencies or f"No agencies on file for state '{state}' and sector '{sector}'. Search the state's attorney general site."
    else:
        result["state"] = "Pass the person's two-letter state code to get state agencies."
    result["warnings"] = warnings
    return result


# ---- rules -------------------------------------------------------------------


def rules_for(reg: Registry, sector: str | None, issue: str | None, state: str | None = None,
              only_issue_points: bool = False) -> dict:
    in_force, not_in_force = [], []
    for r in reg.rules.values():
        juris = r["jurisdiction"]
        if juris not in ("us-federal", "international") and juris != (state or "").lower():
            continue
        applies = r.get("applies_to", {})
        if sector and applies.get("sectors") and sector not in applies["sectors"]:
            continue
        if issue and applies.get("issues") and issue not in applies["issues"]:
            continue
        view = {
            "id": r["id"],
            "title": r["title"],
            "citation": r.get("citation"),
            "jurisdiction": juris,
            "status": r["status"],
            "summary": r["summary"],
            "source": r["source"],
            "last_verified": r["last_verified"],
        }
        if r["status"] in IN_FORCE:
            points = r["points"]
            if only_issue_points and issue:
                points = [p for p in points if not p.get("issues") or issue in p["issues"]]
                if len(points) < len(r["points"]):
                    view["points_omitted"] = len(r["points"]) - len(points)
            view["points"] = points
            in_force.append(view)
        else:
            view["status_note"] = r.get("status_note")
            view["do_not_cite"] = "This rule is not in force. Do not cite it as current law."
            not_in_force.append(view)
    return {"in_force": in_force, "not_in_force": not_in_force}


# ---- escalation --------------------------------------------------------------


def escalation_ladder(reg: Registry, c: dict, state: str | None, today: dt.date, warnings: list[str]) -> list[dict]:
    rungs = c.get("escalation") or reg.sectors[c["sector"]].get("default_escalation", [])
    channels = {ch["id"]: ch for ch in c.get("channels", [])}
    ladder = []
    for i, rung in enumerate(rungs):
        step: dict[str, Any] = {"index": i, "rung": rung["rung"]}
        if rung.get("note"):
            step["note"] = rung["note"]
        if rung.get("channel"):
            ch = channels.get(rung["channel"])
            if ch:
                step["channel"] = _mark(ch, today, warnings, f"{c['id']} channel '{ch['id']}'")
        elif rung["rung"] in ("frontline", "supervisor", "retention", "written_complaint", "executive"):
            # No explicit channel: offer the channels whose label or purpose fits.
            step["candidate_channels"] = [ch["id"] for ch in c.get("channels", []) if _fits(rung["rung"], ch)]
        if rung.get("regulator"):
            step["regulator"] = _regulator_view(reg, rung["regulator"], today, warnings)
        if rung["rung"] == "state_agency":
            kind = rung.get("agency_kind")
            step["agency_kind"] = kind
            if state:
                step["agencies"] = state_agencies(reg, state, c["sector"], kind) or f"No {kind} on file for '{state}'."
            else:
                step["agencies"] = "Ask for the person's state, then call find_regulators."
        if rung["rung"] == "payment_dispute":
            step["rules"] = [r for r in GENERIC_PAYMENT_RULES if r in reg.rules]
        ladder.append(step)
    return ladder


def _fits(rung: str, ch: dict) -> bool:
    label = (ch.get("label", "") + " " + ch.get("notes", "")).lower()
    words = {
        "frontline": ("customer", "service", "support", "help", "chat"),
        "supervisor": ("supervisor", "manager"),
        "retention": ("retention", "loyalty", "cancel"),
        "written_complaint": ("complaint", "feedback", "form", "email", "mail", "dispute", "care"),
        "executive": ("executive", "president", "ceo", "office of", "escalat"),
    }[rung]
    return any(w in label for w in words)


# ---- playbook ----------------------------------------------------------------


def get_playbook(reg: Registry, company: str, issue: str, state: str | None = None, today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    c = resolve_company(reg, company)
    if issue not in reg.issues:
        raise NotFound(f"Unknown issue '{issue}'. Use list_issues(sector='{c['sector']}').")
    generic = reg.issues[issue]
    warnings: list[str] = []
    channels = {ch["id"]: ch for ch in c.get("channels", [])}
    pb = next((p for p in c.get("playbooks", []) if p["issue"] == issue), None)

    if pb:
        steps = []
        for st in pb["steps"]:
            s: dict[str, Any] = {"do": st["do"]}
            if st.get("note"):
                s["note"] = st["note"]
            if st.get("channel") in channels:
                s["channel"] = _mark(channels[st["channel"]], today, warnings, f"channel '{st['channel']}'")
            if st.get("regulator"):
                s["regulator"] = _regulator_view(reg, st["regulator"], today, warnings)
            steps.append(s)
        source = "company"
        evidence = pb.get("evidence") or generic.get("evidence", [])
        summary = pb.get("summary")
    else:
        steps = [{"do": s} for s in generic["steps"]]
        source = "generic"
        evidence = generic.get("evidence", [])
        summary = generic["description"]
        warnings.append(f"No {c['name']} playbook for '{issue}' yet. These are generic steps; use the channels listed below.")

    relevant_channels = [
        _mark(ch, today, warnings, f"channel '{ch['id']}'")
        for ch in c.get("channels", [])
        if not ch.get("purposes") or issue in ch["purposes"]
    ]
    facts = [_mark(f, today, warnings, "company fact") for f in (pb or {}).get("facts", [])]
    facts += [_mark(f, today, warnings, "company fact") for f in c.get("facts", []) if not f.get("issues") or issue in f["issues"]]
    tips = [t for t in c.get("tips", []) if not t.get("issues") or issue in t["issues"]]

    return {
        "company": {"id": c["id"], "name": c["name"], "sector": c["sector"], "website": c["website"], "account_url": c.get("account_url")},
        "issue": {"id": issue, "name": generic["name"]},
        "playbook_source": source,
        "summary": summary,
        "evidence": evidence,
        "steps": steps,
        "channels": relevant_channels,
        "facts": facts,
        "rules": rules_for(reg, c["sector"], issue, state, only_issue_points=True),
        "tips": tips,
        "escalation": escalation_ladder(reg, c, state, today, warnings),
        "known_blockers": c.get("known_blockers", []),
        "security": _security(c),
        "credibility": _credibility(reg, c),
        "context": {
            "dossier": c["id"] in reg.dossiers,
            "sector_guide": c["sector"] in reg.guides,
            "hint": "Call get_context for how this company handles complaints in practice and which scams use its name.",
        },
        "notes": c.get("notes"),
        "warnings": warnings,
    }


def _credibility(reg: Registry, c: dict) -> dict:
    from .credibility import company_credibility

    return company_credibility(reg, c)


def _security(c: dict) -> dict:
    from .context import security_view

    return security_view(c)


def get_context(reg: Registry, company: str | None = None, sector: str | None = None) -> dict:
    """Dossier for a company, the guide for its sector, and the general scam guide."""
    out: dict[str, Any] = {}
    if company:
        c = resolve_company(reg, company)
        sector = sector or c["sector"]
        d = reg.dossiers.get(c["id"])
        out["company"] = {"id": c["id"], "name": c["name"]}
        out["dossier"] = d.body if d else None
        out["dossier_last_verified"] = d.meta.get("last_verified") if d else None
        out["security"] = _security(c)
        out["credibility"] = _credibility(reg, c)
    if sector:
        if sector not in reg.sectors:
            raise NotFound(f"Unknown sector '{sector}'. Known: {', '.join(reg.sectors)}")
        g = reg.guides.get(sector)
        out["sector_guide"] = g.body if g else None
    scams = reg.guides.get("scams")
    out["scam_guide"] = scams.body if scams else None
    if not company and not sector:
        out["available"] = {"dossiers": sorted(reg.dossiers), "guides": sorted(reg.guides)}
    out["how_to_read"] = ("Every bullet cites its source. 'Reported by customers' marks anecdotes from forums: "
                          "useful as tactics to try, not as facts to quote to the company.")
    return out


def get_escalation(reg: Registry, company: str, state: str | None = None, today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    c = resolve_company(reg, company)
    warnings: list[str] = []
    ladder = escalation_ladder(reg, c, state, today, warnings)
    return {"company": c["id"], "state": state, "ladder": ladder, "warnings": warnings}


def next_rung(ladder: list[dict], used: list[str]) -> dict | None:
    """The first rung after the highest rung already used."""
    highest = -1
    for i, step in enumerate(ladder):
        if step["rung"] in used:
            highest = i
    return ladder[highest + 1] if highest + 1 < len(ladder) else None
