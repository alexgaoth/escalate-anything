import datetime as dt
import shutil

import pytest
from mcp import Client

from redress import advisor, context
from redress.registry import Registry
from redress.server import build_server
from redress.store import Store

from .conftest import FIXTURES


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_fixture_docs_load_and_validate(fixture_registry):
    assert set(fixture_registry.dossiers) == {"example-air"}
    assert set(fixture_registry.guides) == {"airline", "scams"}
    assert fixture_registry.validate() == []


def _with_dossier(tmp_path, text):
    root = tmp_path / f"registry-{len(list(tmp_path.iterdir()))}"
    shutil.copytree(FIXTURES, root)
    (root / "dossiers" / "example-air.md").write_text(text)
    return Registry.load(root)


def test_dossier_rules(tmp_path):
    good = (FIXTURES / "dossiers" / "example-air.md").read_text()
    reg = _with_dossier(tmp_path, good.replace("[DOT](https://www.example.gov/rule)", "per DOT"))
    assert any("no source link" in p.message for p in reg.validate())
    reg = _with_dossier(tmp_path, good.replace("Reported by customers: asking", "Asking"))
    assert any("Reported by customers" in p.message for p in reg.validate())
    reg = _with_dossier(tmp_path, good.replace("## Traps and fine print", "## Gossip"))
    msgs = [p.message for p in reg.validate()]
    assert any("missing section '## Traps and fine print'" in m for m in msgs)
    reg = _with_dossier(tmp_path, good.replace("company: example-air", "company: nobody"))
    assert any("front matter 'company'" in p.message for p in reg.validate())


def test_official_domain_must_cover_website(tmp_path):
    root = tmp_path / "registry"
    shutil.copytree(FIXTURES, root)
    path = root / "companies" / "airline" / "example-air.yaml"
    path.write_text(path.read_text().replace("official_domains: [example.com]", "official_domains: [other.com]"))
    assert any("not under any official domain" in p.message for p in Registry.load(root).validate())


@pytest.mark.parametrize("value,company,verdict", [
    ("+1-800-555-0100", "example-air", "on_file"),
    ("1 (800) 555-0100", None, "on_file"),
    ("https://www.example.com/baggage/claim?x=1", "example-air", "on_file"),
    ("https://www.example.com/brand-new-page", "example-air", "official_domain"),
    ("phishing@example.com", "example-air", "on_file"),
    ("https://example-air-refunds.com/claim", "example-air", "lookalike"),
    ("+1-888-555-0199", "example-air", "not_on_file"),
    ("https://www.example.gov/complaint", "example-air", "belongs_to_other"),
])
def test_verify_contact(fixture_registry, value, company, verdict):
    assert context.verify_contact(fixture_registry, value, company)["verdict"] == verdict


def test_scam_check_flags_and_contacts(fixture_registry):
    msg = ("Example Air refund: we refunded you too much by mistake. Send the difference with Google Play gift cards "
           "within 24 hours or your account will be suspended. Call +1 888 555 0199.")
    r = context.scam_check(fixture_registry, msg, "example-air")
    flags = {f["flag"] for f in r["red_flags"]}
    assert {"gift_card", "overpayment", "urgency_threat"} <= flags
    assert r["risk"] == "high"
    assert r["contacts"][0]["verdict"] == "not_on_file"
    calm = context.scam_check(fixture_registry, "Your bag is on the next flight. Track it at https://www.example.com/baggage/claim")
    assert calm["risk"] == "low"


def test_brand_tokens_and_lookalike_verdict(fixture_registry):
    assert context.brand_tokens(fixture_registry.companies["example-air"]) == ["example", "exampleair", "exampleairlines"]
    assert context.brand_tokens({"id": "wells-fargo", "name": "Wells Fargo", "aliases": ["wf bank"]}) == ["wellsfargo", "wfbank"]
    r = context.verify_contact(fixture_registry, "help@example-air.support")
    assert r["verdict"] == "lookalike"
    assert r["advice"] == "This domain imitates Example Air. Do not use it."
    assert r["lookalike"] == [{"company": "example-air", "name": "Example Air", "token": "exampleair", "official": ["example.com"]}]
    # Official and on-file hosts never match, and neither do hosts of other organizations on file.
    for host in ["example.com", "www.example.com", "help.example.com", "example.gov"]:
        assert context.lookalikes(fixture_registry, host) == [], host
    assert context.verify_contact(fixture_registry, "+1-888-555-0199")["verdict"] == "not_on_file"


def test_scam_check_flags_lookalike_domains(fixture_registry):
    r = context.scam_check(fixture_registry, "Claim your refund at https://example-air-refunds.com/claim today.")
    [flag] = [f for f in r["red_flags"] if f["flag"] == "lookalike_domain"]
    assert flag["why"] == "Uses the name Example Air but is not an official Example Air domain (official: example.com)"
    assert flag["matched"] == "https://example-air-refunds.com/claim"
    assert r["risk"] == "high"  # one red flag plus a suspicious (look-alike) contact


@pytest.mark.parametrize("text,flag", [
    ("USPS: your package is held at our warehouse", "package_fee"),
    ("We could not deliver your parcel. Update your address here", "package_fee"),
    ("Pay the $1.99 redelivery fee", "package_fee"),
    ("A customs fee of $3 is due", "package_fee"),
    ("Your toll balance is overdue", "unpaid_toll"),
    ("SunPass: final reminder", "unpaid_toll"),
    ("You have an unpaid toll", "unpaid_toll"),
    ("Please verify your account at https://x.example", "verify_account_link"),
    ("Your card has been restricted. Restore access: https://x.example", "verify_account_link"),
])
def test_new_red_flags(fixture_registry, text, flag):
    assert flag in {f["flag"] for f in context.scam_check(fixture_registry, text)["red_flags"]}


@pytest.mark.parametrize("text", [
    "Your package was delivered to the front door.",
    "We could not deliver your package today. We will try again tomorrow.",
    "Your account settings were updated. Questions? Visit https://www.example.com/help",
])
def test_new_red_flags_stay_quiet(fixture_registry, text):
    assert context.scam_check(fixture_registry, text)["red_flags"] == []


@pytest.fixture(scope="module")
def real_registry():
    return Registry.load()


def test_official_hosts_never_look_alike(real_registry):
    reg = real_registry
    for okind, oid, _name, website, official, channels in context._owner_entries(reg):
        hosts = context._domains(website, official)
        hosts |= {"www." + h for h in hosts}
        hosts |= {u[0] for ch in channels if ch.get("type") in context.URL_CHANNEL_TYPES and (u := context.norm_url(str(ch["value"])))}
        for host in hosts:
            assert context.lookalikes(reg, host) == [], (oid, host)
        if okind == "company" and website:
            assert context.verify_contact(reg, website, oid)["verdict"] != "lookalike", oid
    for c in reg.companies.values():
        assert context.brand_tokens(c), f"{c['id']} has no brand token"


LOOKALIKE_HOSTS = {  # host -> the company it imitates, or None
    "usps-redelivery-fee.com": "usps", "mychase-login.com": "chase", "secure-chaseonline.net": "chase",
    "wells-fargo-alerts.net": "wells-fargo", "amazon-account-verify.com": "amazon",
    "xfinity-support-billing.com": "comcast-xfinity", "paypal.verify-account.io": "paypal",
    "purchase.com": None, "twincities.org": None, "discovery.com": None, "chaseplatform.com": None,
}


@pytest.mark.parametrize("host,company", LOOKALIKE_HOSTS.items())
def test_brand_matching_uses_segments_and_affixes(real_registry, host, company):
    assert [x["company"] for x in context.lookalikes(real_registry, host)] == ([company] if company else [])


def test_brand_candidates():
    assert context.brand_candidates("secure-chaseonline.net") >= {"secure", "chaseonline", "chase", "net"}
    assert "wellsfargo" in context.brand_candidates("wells-fargo-alerts.net")
    assert "chase" not in context.brand_candidates("purchase.com")


@pytest.mark.parametrize("value,company", [
    ("chase-secure-verify.com", "Chase"), ("https://wells-fargo-alerts.net/login", "Wells Fargo"),
    ("https://usps-redelivery-fee.com", "United States Postal Service"), ("billing@xfinity-billing.help", "Xfinity"),
    ("https://paypal.com.account-review.info", "PayPal"),
])
def test_real_lookalikes(real_registry, value, company):
    r = context.verify_contact(real_registry, value)
    assert r["verdict"] == "lookalike" and [x["name"] for x in r["lookalike"]] == [company]


@pytest.mark.parametrize("text,risk", [
    ("USPS: your package is held, pay a $1.99 redelivery fee at https://usps-redelivery-fee.com", "high"),
    ("Your E-ZPass account has an unpaid toll of $4.15. Pay now at https://ezpass-tollpay.top to avoid a $50 fee", "high"),
    ("Amazon: your account has been limited. Verify your identity at https://amazon-account-verify.com", "high"),
    ("Your Amazon order has shipped. Track it at https://www.amazon.com/gp/your-account/order-history", "low"),
])
def test_common_text_scams(real_registry, text, risk):
    assert context.scam_check(real_registry, text)["risk"] == risk


def test_get_context_and_playbook_security(fixture_registry):
    out = advisor.get_context(fixture_registry, "example air")
    assert out["dossier"].startswith("## In short")
    assert out["sector_guide"] and out["scam_guide"]
    assert out["security"]["official_domains"] == ["example.com"]
    pb = advisor.get_playbook(fixture_registry, "example-air", "delayed_baggage")
    assert pb["context"]["dossier"] is True
    assert pb["security"]["never_asks"][0]["claim"].startswith("Example Air never asks")


@pytest.mark.anyio
async def test_tools_and_resources(fixture_registry, tmp_path):
    async with Client(build_server(fixture_registry, Store(tmp_path / "t.db"))) as c:
        names = {t.name for t in (await c.list_tools()).tools}
        assert {"get_context", "verify_contact", "scam_check"} <= names
        r = await c.call_tool("verify_contact", {"value": "+1-800-555-0100", "company": "example-air"})
        assert r.structured_content["verdict"] == "on_file"
        doc = await c.read_resource("redress://dossiers/example-air")
        assert "## What tends to work" in doc.contents[0].text
        prompts = {p.name for p in (await c.list_prompts()).prompts}
        assert "scam-check" in prompts
    async with Client(build_server(fixture_registry, read_only=True)) as c:
        names = {t.name for t in (await c.list_tools()).tools}
        assert {"get_context", "verify_contact", "scam_check"} <= names
