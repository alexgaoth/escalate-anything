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
    ("https://example-air-refunds.com/claim", "example-air", "not_on_file"),
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
