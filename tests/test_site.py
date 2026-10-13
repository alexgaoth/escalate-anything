import json
import re
import shutil
import subprocess

import pytest

from redress import context
from redress.cli import main
from redress.registry import Registry, normalize
from redress.site import WEB_DIR, build_site, index_html

from .conftest import FIXTURES
from .test_context import LOOKALIKE_HOSTS

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node is not installed")

# Loads the DOM-free core of app.js (it exports itself when `module` exists) and runs a list of calls.
# "$C" and "$R" stand for the site's contacts.json and red_flags.json.
JS_RUNNER = r"""
const fs = require("fs");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const mod = { exports: {} };
new Function("module", fs.readFileSync(input.app, "utf8"))(mod);
const core = mod.exports;
const load = (name) => (input.site ? JSON.parse(fs.readFileSync(input.site + "/" + name, "utf8")) : null);
const data = { $C: load("contacts.json"), $R: load("red_flags.json") };
const call = ([fn, ...args]) => core[fn](...args.map((a) => (typeof a === "string" && a in data ? data[a] : a)));
process.stdout.write(JSON.stringify(input.calls.map(call)));
"""


def _js(calls: list, site=None) -> list:
    payload = json.dumps({"app": str(WEB_DIR / "app.js"), "site": str(site) if site else None, "calls": calls})
    proc = subprocess.run([NODE, "-e", JS_RUNNER], input=payload, capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _embedded_data(html: str) -> dict:
    m = re.search(r'<script type="application/json" id="data">(.*?)</script>', html, re.S)
    assert m, "index.html has no embedded data blob"
    return json.loads(m.group(1))


def _fixture_copy(tmp_path, name="registry"):
    root = tmp_path / name
    shutil.copytree(FIXTURES, root)
    return root


def test_build_writes_every_file(tmp_path, fixture_registry):
    counts = build_site(tmp_path, fixture_registry)
    assert counts == {"companies": 1, "states": 1, "issues": len(fixture_registry.issues), "dossiers": 1, "guides": 2}
    for rel in ["index.html", "registry.json", "companies.json", "companies/example-air.json",
                "issues.json", "states/ca.json", "llms.txt", ".nojekyll", "contacts.json", "red_flags.json",
                "dossiers/example-air.md", "guides/airline.md", "guides/scams.md"]:
        assert (tmp_path / rel).is_file(), rel
    assert (tmp_path / "guides" / "scams.md").read_text() == (FIXTURES / "guides" / "scams.md").read_text()


def test_company_json_has_scam_warnings_dossier_and_guide(tmp_path, fixture_registry):
    build_site(tmp_path, fixture_registry)
    doc = json.loads((tmp_path / "companies" / "example-air.json").read_text())
    assert doc["security"]["official_domains"] == ["example.com"]
    assert doc["security"]["never_asks"][0]["claim"].startswith("Example Air never asks")
    assert doc["security"]["report_phishing"][0]["value"] == "phishing@example.com"
    assert doc["dossier"]["markdown"].startswith("## In short")
    assert doc["dossier"]["last_verified"] == "2026-10-01" and doc["dossier"]["file"] == "dossiers/example-air.md"
    assert doc["guide"]["key"] == "airline" and doc["guide"]["page"].endswith("#/guides/airline")
    data = _embedded_data((tmp_path / "index.html").read_text())
    assert [g["key"] for g in data["guides"]] == ["scams", "airline"]
    assert data["dossiers"] == ["example-air"]


def test_build_without_dossiers_guides_or_security(tmp_path):
    root = _fixture_copy(tmp_path)
    shutil.rmtree(root / "dossiers")
    shutil.rmtree(root / "guides")
    path = root / "companies" / "airline" / "example-air.yaml"
    path.write_text(path.read_text().split("\nofficial_domains:")[0] + "\n")
    out = tmp_path / "site"
    counts = build_site(out, Registry.load(root))
    assert counts["dossiers"] == 0 and counts["guides"] == 0
    doc = json.loads((out / "companies" / "example-air.json").read_text())
    assert doc["dossier"] is None and doc["guide"] is None
    assert not any(doc["security"].values())
    assert _embedded_data((out / "index.html").read_text())["guides"] == []
    assert list((out / "guides").iterdir()) == []
    assert "## Guides" not in (out / "llms.txt").read_text()
    assert json.loads((out / "red_flags.json").read_text())["flags"]


def test_contacts_json_is_keyed_by_normalized_value(tmp_path, fixture_registry):
    build_site(tmp_path, fixture_registry)
    contacts = json.loads((tmp_path / "contacts.json").read_text())
    phone = context.norm_phone("+1-800-555-0100")
    assert phone == "8005550100"
    [entry] = contacts["phones"][phone]
    assert entry["owner"] == "example-air" and entry["kind"] == "company" and entry["name"] == "Example Air"
    assert entry["label"] == "Reservations and customer service" and entry["source"] == "https://www.example.com/contact"
    assert {e["path"] for e in contacts["urls"]["example.com"]} >= {"/baggage/claim", "/contact/complaint"}
    assert contacts["emails"]["phishing@example.com"][0]["channel"] == "phishing-email"
    owners = {o["id"]: o for o in contacts["owners"]}
    assert owners["example-air"]["domains"] == ["example.com"]
    assert owners["us-dot"]["kind"] == "regulator"
    assert ["example air", "example-air"] in contacts["aliases"]
    brands = contacts["brands"]
    assert brands["tokens"] == [["exampleairlines", "example-air"], ["exampleair", "example-air"], ["example", "example-air"]]
    assert {"example.com", "example.gov"} <= set(brands["known_hosts"])
    assert "bank" in brands["stopwords"] and brands["affixes"] == list(context.BRAND_AFFIXES)


def test_red_flags_json_comes_from_context(tmp_path, fixture_registry):
    build_site(tmp_path, fixture_registry)
    rf = json.loads((tmp_path / "red_flags.json").read_text())
    assert [(f["id"], f["pattern"], f["why"]) for f in rf["flags"]] == [tuple(x) for x in context.RED_FLAGS]
    assert rf["contact_patterns"] == context.CONTACT_PATTERNS
    assert len(rf["next_steps"]) == 3 and rf["note"].startswith("Pattern checks")
    assert rf["lookalike"]["why"] == context.LOOKALIKE_WHY and rf["lookalike"]["flag"] == "lookalike_domain"
    assert rf["suspicious_verdicts"] == ["not_on_file", "belongs_to_other", "lookalike"]


def test_json_files_parse(tmp_path, fixture_registry):
    build_site(tmp_path, fixture_registry)
    registry = json.loads((tmp_path / "registry.json").read_text())
    assert [c["id"] for c in registry["companies"]] == ["example-air"]

    doc = json.loads((tmp_path / "companies" / "example-air.json").read_text())
    assert doc["company"]["id"] == "example-air"
    assert set(doc["playbooks"]) == {"delayed_baggage"}
    pb = doc["playbooks"]["delayed_baggage"]
    assert pb["playbook_source"] == "company"
    assert pb["steps"][1]["channel"]["id"] == "baggage-claim-form"
    assert [r["rung"] for r in doc["escalation"]] == ["frontline", "written_complaint", "regulator", "payment_dispute"]

    issues = json.loads((tmp_path / "issues.json").read_text())
    assert next(i for i in issues if i["id"] == "delayed_baggage")["companies"] == ["example-air"]
    assert json.loads((tmp_path / "companies.json").read_text())[0]["id"] == "example-air"
    assert json.loads((tmp_path / "states" / "ca.json").read_text())["id"] == "ca"


def test_llms_txt_lists_the_company(tmp_path, fixture_registry):
    build_site(tmp_path, fixture_registry)
    text = (tmp_path / "llms.txt").read_text()
    assert text.startswith("# redress\n\n> ")
    assert "- [Example Air](https://intro.alexgaoth.com/redress/companies/example-air.json)" in text
    assert "approves every message" in text
    assert "[California](https://intro.alexgaoth.com/redress/states/ca.json)" in text
    assert "Verify every contact before you use it" in text
    assert "https://intro.alexgaoth.com/redress/contacts.json" in text
    assert "https://intro.alexgaoth.com/redress/red_flags.json" in text
    assert "- [Common scams](https://intro.alexgaoth.com/redress/guides/scams.md)" in text
    assert "[dossier](https://intro.alexgaoth.com/redress/dossiers/example-air.md)" in text


def test_index_html_is_self_contained(tmp_path, fixture_registry):
    build_site(tmp_path, fixture_registry)
    html = (tmp_path / "index.html").read_text()
    assert not re.search(r"<script\b[^>]*\bsrc\s*=\s*[\"']?(https?:)?//", html, re.I)
    for tag in re.findall(r"<link\b[^>]*>", html, re.I):
        if re.search(r"\brel\s*=\s*[\"']?[^\"'>]*(stylesheet|preload|modulepreload)", tag, re.I):
            assert not re.search(r"\bhref\s*=\s*[\"']?(https?:)?//", tag, re.I), tag
    assert not re.search(r"@import|url\(\s*[\"']?(https?:)?//", html, re.I)
    assert not re.search(r"__[A-Z]+__", html), "a template token was not replaced"
    data = _embedded_data(html)
    assert [c["id"] for c in data["companies"]] == ["example-air"]
    assert data["stats"]["companies"] == 1


def test_embedded_data_cannot_close_the_script(fixture_registry):
    fixture_registry.companies["example-air"]["name"] = "Example </script><script>alert(1)</script>"
    html = index_html(fixture_registry)
    assert "</script><script>alert(1)" not in html
    assert _embedded_data(html)["companies"][0]["name"].startswith("Example </script>")


def test_site_command_builds_the_real_registry(tmp_path):
    assert main(["site", "-o", str(tmp_path)]) == 0
    doc = json.loads((tmp_path / "companies" / "united-airlines.json").read_text())
    assert doc["playbooks"]
    assert "companies/united-airlines.json" in (tmp_path / "llms.txt").read_text()


# ---- the JavaScript in app.js (run with node) ---------------------------------

HOSTILE_DOSSIER = """---
company: example-air
title: Example Air
last_verified: 2026-10-01
---

## In short <script>alert(1)</script>

Plain <img src=x onerror=alert(1)> text with **bold** and a [good link](https://example.com/a?b=1&c="2").

- A bullet with <script>alert(2)</script> and [bad link](javascript:alert(3)) and [data](data:text/html,<b>x</b>).
- [quote break](https://x.com/"onmouseover="alert(4)) and <a href="https://evil.example">raw anchor</a>
<!-- a hidden note <script>alert(5)</script> -->

### Sub **heading**
"""


@needs_node
def test_markdown_renderer_escapes_html(tmp_path):
    root = _fixture_copy(tmp_path)
    (root / "dossiers" / "example-air.md").write_text(HOSTILE_DOSSIER)
    build_site(tmp_path / "site", Registry.load(root))
    markdown = json.loads((tmp_path / "site" / "companies" / "example-air.json").read_text())["dossier"]["markdown"]
    assert "<script>" in markdown  # stored as written; the page escapes it
    [body] = _js([["stripFrontMatter", HOSTILE_DOSSIER]])
    html, guide = _js([["renderMarkdown", markdown, 3], ["renderMarkdown", body, 2]])
    for out in (html, guide):
        assert "<script" not in out.lower()
        assert "<img" not in out and "<b>" not in out
        assert "javascript:" not in out and "data:" not in out
        assert not re.search(r"<[^>]*\son\w+\s*=", out), "an event handler attribute got through"
        assert set(re.findall(r"</?([a-z0-9]+)", out)) <= {"h2", "h3", "h4", "p", "ul", "li", "strong", "a"}
        assert "hidden note" not in out
        assert '<a href="https://example.com/a?b=1&amp;c=&quot;2&quot;" target="_blank" rel="noopener noreferrer">good link</a>' in out
        assert "&lt;a href=&quot;https://evil.example&quot;&gt;raw anchor&lt;/a&gt;" in out
        assert "<strong>bold</strong>" in out
        assert "bad link" in out and "<li>" in out
    assert "<h3>In short &lt;script&gt;alert(1)&lt;/script&gt;</h3>" in html
    assert "<h4>Sub <strong>heading</strong></h4>" in html
    assert "<h2>In short" in guide and "<h3>Sub" in guide


@needs_node
def test_front_matter_is_stripped_like_python(fixture_registry):
    text = (FIXTURES / "guides" / "airline.md").read_text()
    [body, plain] = _js([["stripFrontMatter", text], ["stripFrontMatter", "## No front matter\n"]])
    assert body.strip() == fixture_registry.guides["airline"].body.strip()
    assert plain == "## No front matter\n"


NORMALIZE_SAMPLES = [
    "+1-800-555-0100", "1 (800) 555-0100", "(212) 555 0199 ext 4", "611", "12", "18005550100", "+44 20 7946 0958",
    "٨٠٠٥٥٥٠١٠٠",  # Arabic-Indic digits count as digits in Python
    "https://www.Example.com/Baggage/Claim/?x=1", "example.com", "WWW.EXAMPLE.COM/path/", "  https://united.com/en/us  ",
    "http://user@host.example.com:8080/a#b", "ftp://example.com", "sub.domain.co.uk/x?y", "café.com/x", "not a url",
    "phishing@example.com", " Phishing@Example.COM ", "a@b", "1-800-FLY-DELTA", "﻿https://x.com",
]


@needs_node
def test_js_normalization_matches_python():
    calls = [[fn, v] for v in NORMALIZE_SAMPLES for fn in ("normPhone", "normUrl", "classify", "normName")]
    out = iter(_js(calls))
    for v in NORMALIZE_SAMPLES:
        url = context.norm_url(v)
        assert next(out) == context.norm_phone(v), ("norm_phone", v)
        assert next(out) == (list(url) if url else None), ("norm_url", v)
        assert next(out) == context.classify(v), ("classify", v)
        assert next(out) == normalize(v), ("normalize", v)


def _verdict(r: dict) -> tuple:
    return (r["verdict"], [(m["owner"], m["channel"]) for m in r["matches"]], sorted(d["owner"] for d in r.get("domain_owners", [])),
            [(x["company"], x["name"], x["token"], x["official"]) for x in r.get("lookalike", [])])


def _risk(r: dict) -> tuple:
    return (r["risk"], [(f["flag"], f["matched"], f["why"]) for f in r["red_flags"]],
            [(c["value"], c["verdict"]) for c in r["contacts"]], r["next_steps"], r["note"])


FIXTURE_CONTACTS = [
    ("+1-800-555-0100", "example-air"), ("1 (800) 555-0100", None), ("https://www.example.com/baggage/claim?x=1", "example-air"),
    ("https://www.example.com/brand-new-page", "example-air"), ("phishing@example.com", "example-air"),
    ("https://example-air-refunds.com/claim", "example-air"), ("+1-888-555-0199", "example-air"),
    ("https://www.example.gov/complaint", "example-air"), ("help@mail.example.com", "Example Air"), ("hello", None),
]
FIXTURE_MESSAGES = [
    ("Example Air refund: we refunded you too much by mistake. Send the difference with Google Play gift cards "
     "within 24 hours or your account will be suspended. Call +1 888 555 0199.", "example-air"),
    ("Your bag is on the next flight. Track it at https://www.example.com/baggage/claim", None),
    ("Install AnyDesk so we can help.\nThen read me the one-time code. Email phishing@example.com.", "exampleair"),
]


@needs_node
def test_js_checks_match_python_on_the_fixture(tmp_path, fixture_registry):
    build_site(tmp_path, fixture_registry)
    calls = [["verifyContact", "$C", v, c] for v, c in FIXTURE_CONTACTS]
    calls += [["scamCheck", "$C", "$R", t, c] for t, c in FIXTURE_MESSAGES]
    out = _js(calls, tmp_path)
    for (v, c), js in zip(FIXTURE_CONTACTS, out):
        assert _verdict(js) == _verdict(context.verify_contact(fixture_registry, v, c)), v
    for (t, c), js in zip(FIXTURE_MESSAGES, out[len(FIXTURE_CONTACTS):]):
        assert _risk(js) == _risk(context.scam_check(fixture_registry, t, c)), t
    assert [r["verdict"] for r in out[:8]] == ["on_file", "on_file", "on_file", "official_domain", "on_file",
                                               "lookalike", "not_on_file", "belongs_to_other"]


REAL_CONTACTS = [
    ("1-800-934-6489", "united"), ("1-800-934-6489", "xfinity"), ("1-800-934-6489", None), ("https://www.xfinity.com/support", "comcast"),
    ("https://usps-redelivery-fee.com", "usps"), ("https://www.usps.com/manage/package-intercept.htm", "untied states postal"),
    ("chase-secure-verify.com", None), ("alerts@wells-fargo-alerts.net", "wells fargo"), ("https://ezpass-tollpay.top", None),
    ("https://paypal.com.account-review.info/login", "paypal"), ("https://www.amazon.com/gp/your-account/order-history", "amazon"),
]
SCAM_MESSAGES = [  # (text, company, risk that scam_check must give)
    ("USPS: your package is held, pay a $1.99 redelivery fee at https://usps-redelivery-fee.com", None, "high"),
    ("Your E-ZPass account has an unpaid toll of $4.15. Pay now at https://ezpass-tollpay.top to avoid a $50 fee", None, "high"),
    ("Amazon: your account has been limited. Verify your identity at https://amazon-account-verify.com", None, "high"),
    ("Your Amazon order has shipped. Track it at https://www.amazon.com/gp/your-account/order-history", None, "low"),
]
REAL_MESSAGES = [(t, c) for t, c, _ in SCAM_MESSAGES] + [
    ("Xfinity: your service will be disconnected within 24 hours. Pay with a gift card. Call 1-800-934-6489.", "united"),
    ("Chase fraud alert: confirm your identity at https://chase-secure-verify.com or email help@wellsfargo-alerts.net", "chase"),
]


@needs_node
def test_js_checks_match_python_on_the_real_registry(tmp_path):
    reg = Registry.load()
    build_site(tmp_path, reg)
    queries = ["united", "untied airlines", "verizn", "t mobile", "delta air", "chase", "zzz", ""]
    hosts = list(LOOKALIKE_HOSTS) + sorted(context.brand_index(reg).known_hosts)
    looks = _js([["lookalikes", "$C", h] for h in hosts], tmp_path)
    for host, js in zip(hosts, looks):
        assert js == context.lookalikes(reg, host), host
    assert [[x["company"] for x in js] for js in looks[:len(LOOKALIKE_HOSTS)]] == [[c] if c else [] for c in LOOKALIKE_HOSTS.values()]
    calls = [["findCompany", "$C", q, 5] for q in queries]
    calls += [["verifyContact", "$C", v, c] for v, c in REAL_CONTACTS]
    calls += [["scamCheck", "$C", "$R", t, c] for t, c in REAL_MESSAGES]
    out = iter(_js(calls, tmp_path))
    for q in queries:
        assert next(out) == [c["id"] for c in reg.find_company(q, limit=5)], q
    for v, c in REAL_CONTACTS:
        js = next(out)
        assert _verdict(js) == _verdict(context.verify_contact(reg, v, c)), (v, c)
        if (v, c) == ("1-800-934-6489", "united"):
            assert js["verdict"] == "belongs_to_other" and js["owners"] == ["comcast-xfinity"]
    expected = {t: risk for t, _, risk in SCAM_MESSAGES}
    for t, c in REAL_MESSAGES:
        js = next(out)
        assert _risk(js) == _risk(context.scam_check(reg, t, c)), t
        assert js["risk"] == expected.get(t, js["risk"]), t


def test_badges_are_written(fixture_registry, tmp_path):
    import json

    from redress.site import build_site

    build_site(tmp_path / "out", fixture_registry)
    b = json.loads((tmp_path / "out" / "badges" / "companies.json").read_text())
    assert b == {"schemaVersion": 1, "label": "companies", "message": "1", "color": "2ea44f"}
    assert json.loads((tmp_path / "out" / "badges" / "verified.json").read_text())["message"] == "2026-10-12"
