import pytest
from mcp import Client

from escalate_anything.server import build_server
from escalate_anything.store import Store


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def server(fixture_registry, tmp_path):
    return build_server(fixture_registry, Store(tmp_path / "t.db"))


async def call(client, name, **args):
    result = await client.call_tool(name, args)
    assert not result.is_error, result.content
    return result.structured_content


@pytest.mark.anyio
async def test_tools_are_listed_with_annotations(server):
    async with Client(server) as c:
        tools = {t.name: t for t in (await c.list_tools()).tools}
    assert {"find_company", "get_playbook", "case_open", "draft_brief", "bill_check"} <= set(tools)
    assert tools["get_playbook"].annotations.read_only_hint is True
    assert tools["case_log"].annotations.read_only_hint is False


@pytest.mark.anyio
async def test_case_flow(server):
    async with Client(server) as c:
        found = await call(c, "find_company", query="exampleair")
        assert found["matches"][0]["id"] == "example-air"
        case = await call(c, "case_open", company="Example Air", issue="delayed_baggage",
                          summary="Bag missing", desired_outcome="Reimburse $180", amount=180, state="CA")
        assert case["company"] == "example-air"
        await call(c, "case_log", case_id=case["id"], kind="contact", text="Called", rung="frontline")
        got = await call(c, "case_get", case_id=case["id"])
        assert got["next_rung"]["rung"] == "written_complaint"
        brief = await call(c, "draft_brief", case_id=case["id"])
        assert brief["target"]["rung"] == "written_complaint"
        assert brief["citable_rules"][0]["id"] == "example-refund-rule"
        assert brief["tone_rules"]


@pytest.mark.anyio
async def test_errors_are_readable(server):
    async with Client(server) as c:
        out = await call(c, "get_playbook", company="example-air", issue="nope")
        assert "Unknown issue" in out["error"]
        out = await call(c, "case_log", case_id=999, kind="note", text="x")
        assert out["error"] == "no case 999"


@pytest.mark.anyio
async def test_unlisted_company_case(server):
    async with Client(server) as c:
        case = await call(c, "case_open", company="Joe's Plumbing", issue="refund_request", summary="Deposit not refunded")
        assert case["company"] == "Joe's Plumbing"
        brief = await call(c, "draft_brief", case_id=case["id"])
        assert brief["target"] is None


def test_live_registry_reloads_changed_files(tmp_path):
    import shutil
    import time

    from escalate_anything.server import LiveRegistry

    from .conftest import FIXTURES

    root = tmp_path / "registry"
    shutil.copytree(FIXTURES, root)
    live = LiveRegistry(root)
    live.CHECK_EVERY = 0
    assert live.find_company("example air")[0]["name"] == "Example Air"
    path = root / "companies" / "airline" / "example-air.yaml"
    time.sleep(0.01)
    path.write_text(path.read_text().replace("name: Example Air", "name: Example Airways"))
    assert live.companies["example-air"]["name"] == "Example Airways"
    # A broken edit keeps the last good data.
    time.sleep(0.01)
    path.write_text(path.read_text().replace("sector: airline", "sector: spaceline"))
    assert live.companies["example-air"]["sector"] == "airline"
