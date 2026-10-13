"""Company dossiers, sector guides, and the anti-scam checks built on the registry.

Dossiers (registry/dossiers/<company-id>.md) and guides (registry/guides/<sector>.md, scams.md) are
Markdown with YAML front matter. Every bullet in an evidence section must cite a source link, so
an agent can tell which statements are backed and by what.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

import yaml

if TYPE_CHECKING:
    from .registry import Problem, Registry

DOSSIER_SECTIONS = [
    "In short",
    "How complaints actually go",
    "What tends to work",
    "Traps and fine print",
    "Scams that target customers",
]
GUIDE_SECTIONS = [
    "In short",
    "How complaints work in this industry",
    "Your leverage",
    "Traps",
    "Scams to watch for",
]
OPTIONAL_SECTIONS = {"By the numbers"}
UNCITED_SECTIONS = {"In short"}  # a summary of the cited sections below
FORUM_HOSTS = ("reddit.com", "flyertalk.com", "dslreports.com", "quora.com", "tripadvisor.com", "facebook.com", "x.com", "twitter.com")
LINK_RE = re.compile(r"\]\((https?://[^)\s]+)\)")


@dataclass
class Doc:
    key: str  # company id, sector id or topic
    kind: str  # dossier | guide
    path: Path
    meta: dict
    body: str


def _split_front_matter(text: str) -> tuple[dict, str]:
    if not text.startswith("---\n"):
        raise ValueError("missing YAML front matter (--- ... ---)")
    head, body = text[4:].split("\n---\n", 1)
    from .registry import _Loader  # keeps dates as strings

    return yaml.load(head, Loader=_Loader) or {}, body.strip() + "\n"


def load_docs(root: Path) -> tuple[dict[str, Doc], dict[str, Doc], list[tuple[Path, str]]]:
    dossiers: dict[str, Doc] = {}
    guides: dict[str, Doc] = {}
    errors: list[tuple[Path, str]] = []
    for kind, sub, store in (("dossier", "dossiers", dossiers), ("guide", "guides", guides)):
        for path in sorted((root / sub).glob("*.md")):
            if path.name.upper() == "README.MD":
                continue
            try:
                meta, body = _split_front_matter(path.read_text(encoding="utf-8"))
            except ValueError as e:
                errors.append((path, str(e)))
                continue
            store[path.stem] = Doc(path.stem, kind, path, meta, body)
    return dossiers, guides, errors


def sections(body: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    current = None
    for line in body.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            out[current] = []
        elif current is not None:
            out[current].append(line)
    return out


def validate_doc(doc: Doc, reg: "Registry", today: dt.date) -> list[str]:
    errs: list[str] = []
    meta = doc.meta
    if doc.kind == "dossier":
        if meta.get("company") != doc.key:
            errs.append(f"front matter 'company' must be '{doc.key}'")
        elif doc.key not in reg.companies:
            errs.append(f"no company '{doc.key}' in the registry")
        required = DOSSIER_SECTIONS
    else:
        key = meta.get("sector") or meta.get("topic")
        if key != doc.key:
            errs.append(f"front matter 'sector' (or 'topic') must be '{doc.key}'")
        elif meta.get("sector") and doc.key not in reg.sectors:
            errs.append(f"no sector '{doc.key}'")
        required = GUIDE_SECTIONS if meta.get("sector") else []
    lv = meta.get("last_verified")
    try:
        if dt.date.fromisoformat(str(lv)) > today:
            errs.append(f"last_verified {lv} is in the future")
    except ValueError:
        errs.append("front matter needs last_verified: YYYY-MM-DD")
    if not str(meta.get("title", "")).strip():
        errs.append("front matter needs a title")

    secs = sections(doc.body)
    for name in required:
        if name not in secs:
            errs.append(f"missing section '## {name}'")
    allowed = set(required) | OPTIONAL_SECTIONS if required else None
    for name, lines in secs.items():
        if allowed is not None and name not in allowed:
            errs.append(f"unexpected section '## {name}' (allowed: {', '.join(sorted(allowed))})")
        if name in UNCITED_SECTIONS:
            continue
        for line in lines:
            text = line.strip()
            if not text or text.startswith("<!--"):
                continue
            if not text.startswith("- "):
                errs.append(f"'## {name}': write evidence as bullets ('- ...'), got: {text[:60]}")
                continue
            links = LINK_RE.findall(text)
            if not links:
                errs.append(f"'## {name}': bullet has no source link: {text[:70]}")
            for url in links:
                host = urlsplit(url).netloc.lower()
                if any(host == h or host.endswith("." + h) for h in FORUM_HOSTS) and "Reported by customers" not in text:
                    errs.append(f"'## {name}': forum source needs the words 'Reported by customers': {text[:60]}")
    if len(set(LINK_RE.findall(doc.body))) < 3:
        errs.append("cite at least 3 distinct sources")
    return errs


# ---- contact verification ------------------------------------------------------


def norm_phone(value: str) -> str | None:
    digits = re.sub(r"\D", "", value)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) == 10 or 3 <= len(digits) <= 6:
        return digits
    return None


def norm_url(value: str) -> tuple[str, str] | None:
    v = value.strip()
    if not re.match(r"^https?://", v, re.I):
        if re.match(r"^[\w.-]+\.[a-z]{2,}(/|$)", v, re.I):
            v = "https://" + v
        else:
            return None
    parts = urlsplit(v)
    host = parts.netloc.lower().split("@")[-1].split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    return host, parts.path.rstrip("/").lower()


def classify(value: str) -> str:
    v = value.strip()
    if re.match(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", v, re.I):
        return "email"
    if norm_url(v) and re.search(r"[a-z]", v, re.I):
        return "url"
    if norm_phone(v):
        return "phone"
    return "unknown"


def _owner_entries(reg: "Registry"):
    """(owner kind, owner id, owner name, website, official_domains, channels) for every organization."""
    for c in reg.companies.values():
        channels = list(c.get("channels", [])) + list(c.get("security", {}).get("report_phishing", []))
        yield "company", c["id"], c["name"], c.get("website"), c.get("official_domains", []), channels
    for r in reg.regulators.values():
        yield "regulator", r["id"], r["name"], r.get("website"), [], r.get("channels", [])
    for st in reg.states.values():
        for ag in st["agencies"]:
            yield "state_agency", ag["id"], ag["name"], ag.get("website"), [], ag.get("channels", [])


def _domains(website: str | None, official: list[str]) -> set[str]:
    out = {d.lower() for d in official}
    if website and (n := norm_url(website)):
        out.add(n[0])
    return out


def _host_matches(host: str, domains: set[str]) -> str | None:
    for d in domains:
        if host == d or host.endswith("." + d):
            return d
    return None


def verify_contact(reg: "Registry", value: str, company: str | None = None) -> dict[str, Any]:
    kind = classify(value)
    result: dict[str, Any] = {"value": value, "kind": kind, "matches": []}
    if kind == "unknown":
        result["verdict"] = "unrecognized"
        result["advice"] = "Pass a phone number, an email address or a URL."
        return result
    phone = norm_phone(value) if kind == "phone" else None
    url = norm_url(value) if kind == "url" else None
    email_domain = value.strip().lower().rsplit("@", 1)[-1] if kind == "email" else None

    for okind, oid, oname, website, official, channels in _owner_entries(reg):
        domains = _domains(website, official)
        for ch in channels:
            cv = str(ch.get("value", ""))
            hit = False
            if phone and ch.get("type") in ("phone", "sms", "fax"):
                hit = norm_phone(cv) == phone
            elif url and ch.get("type") in ("web_form", "chat", "portal", "social", "app", "in_person"):
                cu = norm_url(cv)
                hit = bool(cu) and cu[0] == url[0] and (cu[1] == url[1] or url[1].startswith(cu[1] + "/") or not cu[1])
            elif email_domain and ch.get("type") == "email":
                hit = cv.strip().lower() == value.strip().lower()
            if hit:
                result["matches"].append({"owner_kind": okind, "owner": oid, "name": oname, "channel": ch.get("id"),
                                          "label": ch.get("label"), "source": ch.get("source"), "last_verified": ch.get("last_verified")})
        host = url[0] if url else email_domain
        if host and (d := _host_matches(host, domains)):
            result.setdefault("domain_owners", []).append({"owner_kind": okind, "owner": oid, "name": oname, "domain": d})

    # Companies the caller means. An ambiguous name ("united") keeps every candidate.
    targets: set[str] = set()
    if company:
        if company in reg.companies:
            targets = {company}
        else:
            targets = {c["id"] for c in reg.find_company(company, limit=5)}
    owners = {m["owner"] for m in result["matches"]} | {d["owner"] for d in result.get("domain_owners", [])}
    exact_owners = {m["owner"] for m in result["matches"]}

    if exact_owners and (not targets or targets & exact_owners):
        result["verdict"] = "on_file"
        result["advice"] = "This contact is in the registry with a source. Still confirm on the company's own site if it matters."
    elif owners and (not targets or targets & owners):
        result["verdict"] = "official_domain"
        result["advice"] = "The domain belongs to the organization, but this exact address is not on file. Check the full address carefully for look-alike spellings."
    elif targets and owners:
        result["verdict"] = "belongs_to_other"
        result["advice"] = (f"This contact is on file for {', '.join(sorted(owners))}, not for {', '.join(sorted(targets))}. "
                            "Treat it as suspicious.")
    else:
        result["verdict"] = "not_on_file"
        tip = ""
        if len(targets) == 1:
            c = reg.companies[next(iter(targets))]
            tip = f" Use the channels from get_playbook or the company's own site ({c['website']}) instead."
        result["advice"] = ("This contact is not in the registry. Scammers buy search ads and post fake support numbers; "
                            "do not call, click or pay until you confirm it on the organization's official site." + tip)
    return result


# ---- message red flags -------------------------------------------------------

RED_FLAGS: list[tuple[str, str, str]] = [
    ("gift_card", r"\bgift ?cards?\b|\bitunes cards?\b|\bgoogle play cards?\b|\bsteam cards?\b",
     "Asks for payment by gift card. Real companies and government agencies do not take payment in gift cards."),
    ("crypto_or_wire", r"\bbitcoin\b|\bcrypto(currency)?\b|\bbitcoin atm\b|\bwire (the |a )?(money|funds|transfer)\b|\bwestern union\b|\bmoneygram\b",
     "Asks for crypto, a wire transfer or a money transfer service. Money sent this way is very hard to recover."),
    ("p2p_to_yourself", r"\b(zelle|venmo|cash ?app)\b.{0,60}\b(yourself|your own|to protect|safe account|reverse)\b|\b(send|transfer).{0,30}\bto yourself\b",
     "Tells you to send money by Zelle, Venmo or Cash App 'to yourself' or to a 'safe account'. Banks do not ask this."),
    ("remote_access", r"\banydesk\b|\bteamviewer\b|\bscreen ?connect\b|\bremote (access|desktop|control)\b|\bquick ?assist\b",
     "Asks you to install remote-access software. Do not let anyone control your device."),
    ("credentials", r"\b(one[- ]time|verification|security|2fa|otp) ?(code|passcode|pin)\b|\bpassword\b|\bsocial security number\b|\bssn\b|\bfull card number\b",
     "Asks for a code, password, PIN or SSN. Companies that text you a code do not call to ask for it."),
    ("pay_to_get_refund", r"\b(fee|pay|payment).{0,40}\b(release|process|receive|unlock).{0,20}\b(refund|compensation|funds|claim)\b|\brecovery (service|fee)\b",
     "Asks you to pay to receive a refund or to recover lost money. That is a common follow-up scam."),
    ("overpayment", r"\b(refunded|sent|deposited) (you )?(too much|extra|by mistake)\b|\boverpa(id|yment)\b",
     "Claims they refunded too much and you must send the difference back. This is a common refund scam."),
    ("urgency_threat", r"\b(within|in) (24|48) hours\b|\bimmediately\b.{0,40}\b(suspend|disconnect|arrest|close)\b|\b(account|service) (will be|has been) (suspended|locked|disconnected)\b|\bfinal notice\b",
     "Pressure: threatens suspension, shutoff, arrest or a deadline. Pressure is a scam tactic; check through the official channel."),
    ("utility_shutoff_payment", r"\b(disconnect|shut ?off|cut off)\b.{0,80}\b(gift card|prepaid card|bitcoin|cash app|zelle|venmo)\b",
     "Threatens a utility shutoff unless you pay by an unusual method. Utilities send written notices and take normal payments."),
    ("link_lookalike", r"https?://[^\s]*(-support|-help|-refund|-verify|secure-|login-)[^\s]*",
     "Contains a link with words like support, refund, verify or login in the domain. Check the exact domain against the official one."),
]


def scam_check(reg: "Registry", text: str, company: str | None = None) -> dict[str, Any]:
    flags = []
    lowered = text.lower()
    for fid, pattern, why in RED_FLAGS:
        m = re.search(pattern, lowered, re.I | re.S)
        if m:
            flags.append({"flag": fid, "why": why, "matched": text[max(0, m.start() - 20):m.end() + 20].strip()})
    contacts = set()
    contacts.update(re.findall(r"https?://[^\s)>\]\"']+", text))
    contacts.update(re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", text))
    contacts.update(m.strip() for m in re.findall(r"(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}", text))
    checks = [verify_contact(reg, c.rstrip(".,;"), company) for c in sorted(contacts)]
    suspicious = [c for c in checks if c["verdict"] in ("not_on_file", "belongs_to_other")]
    level = "high" if flags and (suspicious or len(flags) >= 2) else "medium" if flags or suspicious else "low"
    return {
        "risk": level,
        "red_flags": flags,
        "contacts": checks,
        "next_steps": [
            "Do not reply, call, click or pay from the message itself.",
            "Contact the organization through a channel from get_playbook or its official website.",
            "If money or data was already given: call your bank's fraud line now, then report at ReportFraud.ftc.gov.",
        ] if level != "low" else ["No common red flags found. Still use official channels for anything involving money or account access."],
        "note": "Pattern checks catch common scams, not all of them. A 'low' result is not proof that a message is genuine.",
    }


def security_view(company: dict) -> dict[str, Any]:
    sec = company.get("security", {})
    return {
        "official_domains": company.get("official_domains", []),
        "never_asks": sec.get("never_asks", []),
        "known_scams": sec.get("known_scams", []),
        "report_phishing": sec.get("report_phishing", []),
    }
