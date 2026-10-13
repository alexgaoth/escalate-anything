import re
from pathlib import Path

import pytest
from mcp import Client

from redress.server import build_server
from redress.store import Store

SKILLS = sorted((Path(__file__).parents[1] / "skills").glob("*/SKILL.md"))


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_skills_have_frontmatter():
    assert len(SKILLS) == 4
    for path in SKILLS:
        text = path.read_text()
        m = re.match(r"---\nname: ([a-z-]+)\ndescription: (.+?)\n---\n", text, re.S)
        assert m, f"{path} needs name and description frontmatter"
        assert m.group(1) == path.parent.name
        assert len(m.group(2)) < 1024


@pytest.mark.anyio
async def test_skills_call_only_real_tools(fixture_registry, tmp_path):
    async with Client(build_server(fixture_registry, Store(tmp_path / "t.db"))) as c:
        tools = {t.name for t in (await c.list_tools()).tools}
    for path in SKILLS:
        called = set(re.findall(r"`([a-z_]+)\(", path.read_text()))
        mentioned = {w for w in re.findall(r"`([a-z]+_[a-z_]+)`", path.read_text()) if w.split("_")[0] in {"case", "find", "get", "list", "bill", "draft", "report", "followups"} and w not in fixture_registry.issues}
        assert (called | mentioned) <= tools, f"{path.parent.name} names unknown tools: {(called | mentioned) - tools}"
