"""How much to trust an entry: source tiers, verification signals and dates.

Every sourced value (channel, fact, tip, security item, dossier link) is classified:
  primary    the organization's own domains, government sites, and regulators such as FINRA
  reference  law-text mirrors, BBB, research organizations, reputable news, press-release wires,
             or another company's own domain
  community  forums (always marked "Reported by customers" in dossiers)
  other      anything else
Values read from a search-result snippet or an archive copy are counted separately, because
nobody saw the live page.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from .registry import Registry

STALE_DAYS = 180

GOV_LIKE = {
    "finra.org", "icao.int", "naic.org", "nmlsconsumeraccess.org", "annualcreditreport.com",
    "identitytheft.gov", "consumerfinance.gov", "uscourts.gov", "supremecourt.gov",
}
REFERENCE = {
    # law text and court records
    "law.cornell.edu", "california.public.law", "justia.com", "law.justia.com", "courtlistener.com",
    "casetext.com", "laws-lois.justice.gc.ca",
    # consumer and research organizations
    "bbb.org", "bbbmarketplacetrust.org", "consumerreports.org", "kff.org", "theacsi.org", "jdpower.com",
    "consumerfed.org", "nclc.org", "ticas.org", "aarp.org", "pewresearch.org", "urban.org",
    # press-release wires (the company's own words on a third-party host)
    "prnewswire.com", "businesswire.com", "globenewswire.com",
    # news
    "reuters.com", "apnews.com", "nytimes.com", "wsj.com", "washingtonpost.com", "bloomberg.com",
    "cnbc.com", "npr.org", "cnn.com", "nbcnews.com", "cbsnews.com", "abcnews.go.com", "usatoday.com",
    "latimes.com", "theverge.com", "arstechnica.com", "techcrunch.com", "fiercewireless.com",
    "lightreading.com", "bankingdive.com", "paymentsdive.com", "americanbanker.com",
    "bankingjournal.aba.com", "thepointsguy.com", "nerdwallet.com",
}
COMMUNITY = {"reddit.com", "flyertalk.com", "dslreports.com", "quora.com", "tripadvisor.com", "facebook.com", "x.com", "twitter.com"}
ARCHIVE = {"web.archive.org", "archive.org", "archive.ph", "archive.today"}
SNIPPET_RE = re.compile(r"search[- ](result|snippet|excerpt)|\bsnippet\b|search text", re.I)
ARCHIVE_RE = re.compile(r"wayback|archive copy|archived copy|archive\.org", re.I)
STATE_US_RE = re.compile(r"\.(state|k12|ci|co|cty|town|city)\.[a-z]{2}\.us$")


def host_of(url: str) -> str:
    h = urlsplit(url).netloc.lower().split("@")[-1].split(":")[0]
    return h[4:] if h.startswith("www.") else h


def _under(h: str, domains) -> bool:
    return any(h == d or h.endswith("." + d) for d in domains)


def org_domains(org: dict) -> set[str]:
    out = {d.lower() for d in org.get("official_domains", [])}
    if org.get("website"):
        out.add(host_of(org["website"]))
    return out


def classify(url: str, own: set[str], others: set[str] | None = None) -> str:
    h = host_of(url)
    if _under(h, ARCHIVE):
        return "archive"
    if own and _under(h, own):
        return "primary"
    if h.endswith((".gov", ".mil")) or ".gov." in h or STATE_US_RE.search(h) or _under(h, GOV_LIKE):
        return "primary"
    if _under(h, COMMUNITY):
        return "community"
    if _under(h, REFERENCE) or (others and _under(h, others)):
        return "reference"
    return "other"


def verification_signal(item: dict) -> str:
    """page, search_snippet or archive, from verified_via or from the item's own wording."""
    explicit = item.get("verified_via")
    if explicit:
        return explicit
    text = " ".join(str(item.get(k, "")) for k in ("notes", "claim", "text", "label"))
    if _under(host_of(item.get("source", "")), ARCHIVE) or ARCHIVE_RE.search(text):
        return "archive"
    if SNIPPET_RE.search(text):
        return "search_snippet"
    return "page"


def _walk(node: Any):
    if isinstance(node, dict):
        if "source" in node and "last_verified" in node:
            yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def _all_company_domains(reg: "Registry") -> set[str]:
    out: set[str] = set()
    for c in reg.companies.values():
        out |= org_domains(c)
    return out


def summarize(items: list[dict], own: set[str], others: set[str], links: list[str], dates_extra: list[str],
              today: dt.date) -> dict[str, Any]:
    tiers = {"primary": 0, "reference": 0, "community": 0, "other": 0, "archive": 0}
    signals = {"page": 0, "search_snippet": 0, "archive": 0}
    dates: list[dt.date] = []
    stale = 0
    for it in items:
        tiers[classify(it["source"], own, others)] += 1
        signals[verification_signal(it)] = signals.get(verification_signal(it), 0) + 1
        try:
            d = dt.date.fromisoformat(str(it["last_verified"]))
        except ValueError:
            continue
        dates.append(d)
        if (today - d).days > STALE_DAYS:
            stale += 1
    for url in links:
        tiers[classify(url, own, others)] += 1
    for s in dates_extra:
        try:
            dates.append(dt.date.fromisoformat(str(s)))
        except ValueError:
            pass
    total = sum(tiers.values())
    primary_share = tiers["primary"] / total if total else 0.0
    weak = (signals["search_snippet"] + signals["archive"]) / max(len(items), 1)
    if total >= 10 and primary_share >= 0.9 and weak <= 0.05 and stale == 0:
        grade = "A"
    elif total >= 5 and primary_share >= 0.75 and weak <= 0.15:
        grade = "B"
    else:
        grade = "C"
    return {
        "grade": grade,
        "primary_share": round(primary_share, 3),
        "sources": {k: v for k, v in tiers.items() if v},
        "verified_from": {k: v for k, v in signals.items() if v},
        "last_verified": max(dates).isoformat() if dates else None,
        "oldest_verified": min(dates).isoformat() if dates else None,
        "stale_items": stale,
        "explanation": _explain(grade, primary_share, signals, stale, total),
    }


def _explain(grade: str, share: float, signals: dict, stale: int, total: int) -> str:
    parts = [f"{round(share * 100)}% of {total} sources are the organization's own pages or government sites"]
    if total < 10:
        parts.append(f"only {total} sourced values, so the entry is thin")
    weak = signals.get("search_snippet", 0) + signals.get("archive", 0)
    if weak:
        parts.append(f"{weak} value(s) were read from a search snippet or an archive copy")
    if stale:
        parts.append(f"{stale} value(s) are older than {STALE_DAYS} days")
    meaning = {"A": "high: almost everything comes from official pages read directly",
               "B": "good: mostly official pages; check the flagged values before relying on them",
               "C": "use with care: check the source of each value before relying on it"}[grade]
    return f"Grade {grade} ({meaning}). " + "; ".join(parts) + "."


def company_credibility(reg: "Registry", company: dict, today: dt.date | None = None) -> dict[str, Any]:
    from .context import LINK_RE

    today = today or dt.date.today()
    own = org_domains(company)
    others = _all_company_domains(reg) - own
    items = list(_walk(company))
    doc = reg.dossiers.get(company["id"])
    links = LINK_RE.findall(doc.body) if doc else []
    extra = [doc.meta.get("last_verified")] if doc else []
    out = summarize(items, own, others, links, extra, today)
    out["dossier_last_verified"] = str(doc.meta.get("last_verified")) if doc else None
    return out


def registry_credibility(reg: "Registry", today: dt.date | None = None) -> dict[str, Any]:
    today = today or dt.date.today()
    grades = {"A": 0, "B": 0, "C": 0}
    newest, oldest = None, None
    for c in reg.companies.values():
        cc = company_credibility(reg, c, today)
        grades[cc["grade"]] += 1
        if cc["last_verified"]:
            newest = max(newest or cc["last_verified"], cc["last_verified"])
            oldest = min(oldest or cc["oldest_verified"], cc["oldest_verified"])
    return {"grades": grades, "last_verified": newest, "oldest_verified": oldest}
