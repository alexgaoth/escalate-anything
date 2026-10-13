import json

import pytest
from mcp import Client

from escalate_anything import cli
from escalate_anything.server import WRITE_TOOLS, build_server, load_skills
from escalate_anything.store import Store


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_skills_load_as_prompts_source():
    names = {s["name"] for s in load_skills()}
    assert names == {"resolve", "negotiate-bill", "regulator-complaint", "bill-watch", "scam-check"}


@pytest.mark.anyio
async def test_prompts_and_resources(fixture_registry, tmp_path):
    async with Client(build_server(fixture_registry, Store(tmp_path / "t.db"))) as c:
        prompts = {p.name for p in (await c.list_prompts()).prompts}
        assert {"resolve", "negotiate-bill", "regulator-complaint", "bill-watch"} <= prompts
        got = await c.get_prompt("resolve", {"situation": "United lost my bag"})
        text = got.messages[0].content.text
        assert "get_playbook" in text and "United lost my bag" in text
        index = await c.read_resource("escalate://companies")
        assert json.loads(index.contents[0].text)[0]["id"] == "example-air"
        one = await c.read_resource("escalate://companies/example-air")
        assert json.loads(one.contents[0].text)["name"] == "Example Air"


@pytest.mark.anyio
async def test_read_only_server_has_no_write_tools(fixture_registry):
    async with Client(build_server(fixture_registry, read_only=True)) as c:
        tools = {t.name for t in (await c.list_tools()).tools}
        assert tools.isdisjoint(WRITE_TOOLS)
        assert {"find_company", "get_playbook", "get_rules"} <= tools
        got = await c.get_prompt("resolve", {})
        assert "read-only" in got.messages[0].content.text


def test_cli_playbook_and_lookup(capsys, monkeypatch):
    from .conftest import FIXTURES

    monkeypatch.setenv("ESCALATE_REGISTRY", str(FIXTURES))
    assert cli.main(["playbook", "exampleair", "delayed_baggage", "--state", "CA"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("# Example Air: Delayed bag") and "## Steps" in out and "baggage/claim" in out
    assert cli.main(["lookup", "example"]) == 0
    assert "example-air" in capsys.readouterr().out
    assert cli.main(["playbook", "nobody", "billing_error"]) == 1
