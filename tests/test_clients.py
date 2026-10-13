import json

import pytest

from redress import clients
from redress.clients import CLIENTS, install, snippet


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData" / "Roaming"))
    monkeypatch.delenv("CLINE_MCP_SETTINGS_PATH", raising=False)
    monkeypatch.delenv("CODEX_HOME", raising=False)
    return tmp_path


CMD, ARGS = "uvx", ["redress-mcp"]


def test_json_merge_keeps_other_settings_and_backs_up(home):
    path = CLIENTS["cursor"].config_path(home)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}, "theme": "dark"}))
    r = install("cursor", CMD, ARGS, home=home)
    assert r.status == "installed"
    data = json.loads(path.read_text())
    assert data["theme"] == "dark" and "other" in data["mcpServers"]
    assert data["mcpServers"]["redress"] == {"type": "stdio", "command": "uvx", "args": ["redress-mcp"]}
    assert list(path.parent.glob("mcp.json.bak-redress-*"))
    assert install("cursor", CMD, ARGS, home=home).status == "unchanged"
    assert install("cursor", CMD, ARGS, home=home, remove=True).status == "removed"
    assert "redress" not in json.loads(path.read_text())["mcpServers"]


def test_vscode_uses_servers_key(home):
    r = install("vscode", CMD, ARGS, home=home)
    data = json.loads(open(r.path).read())
    assert "servers" in data and "mcpServers" not in data


def test_claude_desktop_keeps_preferences(home):
    path = CLIENTS["claude-desktop"].config_path(home)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"preferences": {"x": 1}}))
    install("claude-desktop", CMD, ARGS, home=home)
    data = json.loads(path.read_text())
    assert data["preferences"] == {"x": 1} and data["mcpServers"]["redress"]["command"] == "uvx"


def test_jsonc_with_comments_is_not_rewritten(home):
    path = CLIENTS["zed"].config_path(home)
    path.parent.mkdir(parents=True)
    original = '{\n  // my theme\n  "theme": "One Dark"\n}\n'
    path.write_text(original)
    r = install("zed", CMD, ARGS, home=home)
    assert r.status == "manual" and '"context_servers"' in r.message
    assert path.read_text() == original
    # URLs inside strings are not comments
    path.write_text('{"theme": "One Dark", "url": "https://zed.dev"}')
    assert install("zed", CMD, ARGS, home=home).status == "installed"


def test_codex_toml_append_and_remove(home):
    path = CLIENTS["codex"].config_path(home)
    path.parent.mkdir(parents=True)
    path.write_text('model = "gpt-5"\n\n[mcp_servers.other]\ncommand = "x"\n')
    assert install("codex", CMD, ARGS, home=home).status == "installed"
    text = path.read_text()
    assert '[mcp_servers.redress]\ncommand = "uvx"\nargs = ["redress-mcp"]' in text and 'model = "gpt-5"' in text
    assert install("codex", CMD, ARGS, home=home).status == "unchanged"
    assert install("codex", CMD, ARGS, home=home, remove=True).status == "removed"
    assert "redress" not in path.read_text() and "[mcp_servers.other]" in path.read_text()


def test_yaml_clients_get_a_snippet(home):
    r = install("goose", CMD, ARGS, home=home)
    assert r.status == "manual" and "extensions:" in r.message and "cmd: uvx" in r.message


def test_invalid_json_is_left_alone(home):
    path = CLIENTS["lmstudio"].config_path(home)
    path.parent.mkdir(parents=True)
    path.write_text("{not json")
    assert install("lmstudio", CMD, ARGS, home=home).status == "error"
    assert path.read_text() == "{not json"


def test_claude_code_dry_run_and_snippets():
    assert install("claude-code", CMD, ARGS, dry_run=True).message == "Would run: claude mcp add --scope user redress -- uvx redress-mcp"
    for cid, client in CLIENTS.items():
        assert snippet(client, CMD, ARGS), cid


def test_server_command_sources():
    cmd, args = clients.server_command("pypi")
    assert args == ["redress-mcp"]
    cmd, args = clients.server_command("git", read_only=True)
    assert args[:2] == ["--from", clients.GIT_SOURCE] and args[-1] == "--read-only"
    cmd, args = clients.server_command("auto")  # tests run from the checkout
    assert "--directory" in args
