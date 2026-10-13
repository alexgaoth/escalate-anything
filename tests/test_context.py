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


def test_scam_check_flags(fixture_registry):
    msg = ("Example Air refund: we refunded you too much by mistake. Send the difference with Google Play gift cards "
           "within 24 hours or your account will be suspended. Call +1 888 555 0199.")
    r = context.scam_check(fixture_registry, msg, "example-air")
    flags = {f["flag"] for f in r["red_flags"]}
    assert {"gift_card", "overpayment", "urgency_threat"} <= flags
    assert r["risk"] == "high"
    assert "contacts" not in r
    calm = context.scam_check(fixture_registry, "Your bag is on the next flight. Track it at https://www.example.com/baggage/claim")
    assert calm["risk"] == "low"


def test_contact_checker_is_gone():
    assert not hasattr(context, "verify_contact")
    assert not any(fid == "link_lookalike" for fid, _, _ in context.RED_FLAGS)


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


@pytest.mark.parametrize("text,risk", [
    ("USPS: your package is held, pay a $1.99 redelivery fee at https://usps-redelivery-fee.com", "flagged"),
    ("Your E-ZPass account has an unpaid toll of $4.15. Pay now at https://ezpass-tollpay.top to avoid a $50 fee", "flagged"),
    ("Amazon: your account has been limited. Verify your identity at https://amazon-account-verify.com", "flagged"),
    ("Your Amazon order has shipped. Track it at https://www.amazon.com/gp/your-account/order-history", "low"),
])
def test_common_text_scams(real_registry, text, risk):
    got = context.scam_check(real_registry, text)["risk"]
    assert got == "low" if risk == "low" else got in ("medium", "high")


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
        assert {"get_context", "scam_check"} <= names and "verify_contact" not in names
        doc = await c.read_resource("redress://dossiers/example-air")
        assert "## What tends to work" in doc.contents[0].text
        prompts = {p.name for p in (await c.list_prompts()).prompts}
        assert "scam-check" in prompts
    async with Client(build_server(fixture_registry, read_only=True)) as c:
        names = {t.name for t in (await c.list_tools()).tools}
        assert {"get_context", "scam_check"} <= names
