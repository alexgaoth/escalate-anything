"""Company dossiers, sector guides, and a simple scam red-flag check (a side feature).

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
    ("package_fee",
     r"\bre-?deliver(y|ing)? (fee|charge|payment)\b"
     r"|\b(package|parcel|shipment|delivery)\b.{0,40}\b(is|was|has been|being) (held|on hold)\b"
     r"|\b(could not|couldn['’]t|cannot|can['’]t|unable to|failed to|was not|wasn['’]t) (be )?deliver(ed)?\b.{0,120}"
     r"\b(fee|pay|payment|update (your )?(address|details|information)|confirm (your )?(address|details))\b"
     r"|\bcustoms (fee|charge|duty|duties)\b",
     "Says a package is held or could not be delivered and asks for a fee or an address update. Carriers do not text "
     "links to pay redelivery or customs fees. Track the package on the carrier's own website."),
    ("unpaid_toll",
     r"\bunpaid tolls?\b|\btoll (balance|bill|charge|due|fee|invoice|notice|payment|violation)s?\b"
     r"|\be-?z ?pass\b|\bsun ?pass\b|\bfas ?trak\b",
     "Says you owe a toll. Toll agencies such as E-ZPass, SunPass and FasTrak do not text links for payment. "
     "Check your balance on the agency's own website or app."),
    ("verify_account_link",
     r"\b(verify|confirm|validate|reactivate|unlock|restore) (your )?(account|identity|login|information|details|billing|payment (method|details))\b.{0,200}https?://"
     r"|\b(account|card|access)\b.{0,20}\b(has been|have been|is|was) (temporarily )?(limited|restricted|locked|suspended|disabled|on hold)\b.{0,200}https?://"
     r"|https?://\S+.{0,100}\b(verify|confirm|validate) (your )?(account|identity)\b",
     "Asks you to verify your account or identity through a link. Do not sign in or give details from a link in a "
     "message. Open the company's app, or type its address yourself."),
]


def scam_check(reg: "Registry", text: str, company: str | None = None) -> dict[str, Any]:
    """Common red flags in a message (gift cards, crypto, remote access, codes, pressure...)."""
    flags = []
    lowered = text.lower()
    for fid, pattern, why in RED_FLAGS:
        m = re.search(pattern, lowered, re.I | re.S)
        if m:
            flags.append({"flag": fid, "why": why, "matched": text[max(0, m.start() - 20):m.end() + 20].strip()})
    level = "high" if len(flags) >= 2 else "medium" if flags else "low"
    return {
        "risk": level,
        "red_flags": flags,
        "next_steps": [
            "Do not reply, call, click or pay from the message itself.",
            "Contact the company through a channel from get_playbook or its own website.",
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
