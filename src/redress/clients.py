"""Add the redress MCP server to the person's AI apps: `redress install <client>`.

Config locations and shapes were checked against each client's docs on 2026-10-12 (see docs/clients.md).
JSON files are merged, never replaced, and backed up first. Files that may hold comments (JSONC) or
YAML are not rewritten; for those we print the snippet to paste instead.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .registry import REPO_ROOT, data_root

NAME = "redress"
GIT_SOURCE = "git+https://github.com/alexgaoth/redress"


def server_command(source: str = "auto", read_only: bool = False) -> tuple[str, list[str]]:
    """How a client should start the server.

    auto: the local checkout when running from source, else the PyPI package via uvx.
    """
    extra = ["--read-only"] if read_only else []
    if source == "auto":
        source = "local" if data_root() == REPO_ROOT else "pypi"
    if source == "local":
        uv = shutil.which("uv") or "uv"
        return uv, ["run", "--quiet", "--directory", str(REPO_ROOT), "redress-mcp", *extra]
    uvx = shutil.which("uvx") or "uvx"
    if source == "git":
        return uvx, ["--from", GIT_SOURCE, "redress-mcp", *extra]
    return uvx, ["redress-mcp", *extra]


def _os() -> str:
    return {"Darwin": "mac", "Windows": "win"}.get(platform.system(), "linux")


def _appdata(home: Path) -> Path:
    return Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))


def _xdg(home: Path) -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))


@dataclass
class Client:
    id: str
    label: str
    paths: Callable[[Path], list[Path]]  # candidate config files; the first is where we write
    fmt: str  # json | jsonc | toml | yaml | cli
    entry: Callable[[str, list[str]], dict] = field(default=lambda cmd, args: {"command": cmd, "args": args})
    key: str = "mcpServers"
    restart: str = ""
    detect: Callable[[Path], list[Path]] | None = None  # directories whose presence means "installed"

    def config_path(self, home: Path) -> Path:
        return self.paths(home)[0]

    def detected(self, home: Path) -> bool:
        dirs = self.detect(home) if self.detect else [p.parent for p in self.paths(home)]
        return any(d.exists() for d in dirs)


def _vscode_user(home: Path) -> Path:
    return {"mac": home / "Library/Application Support/Code/User", "win": _appdata(home) / "Code/User"}.get(_os(), _xdg(home) / "Code/User")


CLIENTS: dict[str, Client] = {c.id: c for c in [
    Client("claude-desktop", "Claude Desktop",
           lambda h: [{"mac": h / "Library/Application Support/Claude", "win": _appdata(h) / "Claude"}.get(_os(), _xdg(h) / "Claude") / "claude_desktop_config.json"],
           "json", restart="Quit Claude Desktop completely (Cmd+Q / exit from the tray) and open it again."),
    Client("claude-code", "Claude Code", lambda h: [h / ".claude.json"], "cli",
           detect=lambda h: [h / ".claude"]),
    Client("cursor", "Cursor", lambda h: [h / ".cursor/mcp.json"], "json",
           entry=lambda cmd, args: {"type": "stdio", "command": cmd, "args": args}),
    Client("vscode", "VS Code (GitHub Copilot)", lambda h: [_vscode_user(h) / "mcp.json"], "json",
           entry=lambda cmd, args: {"type": "stdio", "command": cmd, "args": args}, key="servers",
           restart="VS Code asks you to trust and start the server the first time."),
    Client("windsurf", "Windsurf / Devin Desktop",
           lambda h: [({"win": _appdata(h) / "devin"}.get(_os(), _xdg(h) / "devin")) / "mcp_config.json",
                      h / ".codeium/windsurf/mcp_config.json", h / ".codeium/mcp_config.json"],
           "json", restart="Refresh the MCP list in Cascade, or restart the app.",
           detect=lambda h: [_xdg(h) / "devin", _appdata(h) / "devin", h / ".codeium"]),
    Client("cline", "Cline", lambda h: [Path(os.environ.get("CLINE_MCP_SETTINGS_PATH", h / ".cline/data/settings/cline_mcp_settings.json"))],
           "json", entry=lambda cmd, args: {"type": "stdio", "command": cmd, "args": args, "disabled": False, "autoApprove": []},
           detect=lambda h: [h / ".cline"]),
    Client("gemini", "Gemini CLI", lambda h: [h / ".gemini/settings.json"], "jsonc"),
    Client("zed", "Zed", lambda h: [(_appdata(h) / "Zed" if _os() == "win" else _xdg(h) / "zed") / "settings.json"], "jsonc",
           entry=lambda cmd, args: {"command": cmd, "args": args, "env": {}}, key="context_servers"),
    Client("codex", "OpenAI Codex (CLI, IDE extension, desktop app)", lambda h: [Path(os.environ.get("CODEX_HOME", h / ".codex")) / "config.toml"],
           "toml", restart="Restart the Codex desktop app or IDE extension."),
    Client("lmstudio", "LM Studio", lambda h: [h / ".lmstudio/mcp.json"], "json"),
    Client("junie", "JetBrains Junie", lambda h: [h / ".junie/mcp/mcp.json"], "json"),
    Client("goose", "Goose", lambda h: [(_appdata(h) / "Block/goose/config" if _os() == "win" else _xdg(h) / "goose") / "config.yaml"], "yaml"),
    Client("continue", "Continue", lambda h: [h / ".continue/config.yaml"], "yaml"),
]}


def snippet(client: Client, cmd: str, args: list[str]) -> str:
    entry = client.entry(cmd, args)
    if client.fmt in ("json", "jsonc"):
        return json.dumps({client.key: {NAME: entry}}, indent=2)
    if client.fmt == "toml":
        return f'[mcp_servers.{NAME}]\ncommand = {json.dumps(cmd)}\nargs = {json.dumps(args)}\n'
    if client.id == "goose":
        return ("extensions:\n  redress:\n    name: redress\n    type: stdio\n"
                f"    cmd: {cmd}\n    args: {json.dumps(args)}\n    enabled: true\n    envs: {{}}\n    timeout: 300\n")
    if client.id == "continue":
        return f"mcpServers:\n  - name: redress\n    type: stdio\n    command: {cmd}\n    args: {json.dumps(args)}\n"
    if client.id == "claude-code":
        return " ".join(["claude", "mcp", "add", "--scope", "user", NAME, "--", cmd, *args])
    return ""


def _backup(path: Path) -> Path:
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = path.with_name(f"{path.name}.bak-redress-{stamp}")
    shutil.copy2(path, dest)
    return dest


def _has_comments(text: str) -> bool:
    # Strip strings first so URLs like "https://" do not count as comments.
    no_strings = re.sub(r'"(?:\\.|[^"\\])*"', '""', text)
    return bool(re.search(r"//|/\*", no_strings))


@dataclass
class Result:
    client: str
    status: str  # installed | updated | unchanged | removed | manual | skipped | error
    path: str | None
    message: str


def install(client_id: str, cmd: str, args: list[str], home: Path | None = None, dry_run: bool = False,
            remove: bool = False) -> Result:
    home = home or Path.home()
    client = CLIENTS[client_id]
    path = client.config_path(home)

    if client.fmt == "cli":
        line = snippet(client, cmd, args)
        if dry_run:
            return Result(client_id, "manual", None, f"Would run: {line}")
        exe = shutil.which("claude")
        if not exe:
            return Result(client_id, "skipped", None, f"`claude` not found. Run later: {line}")
        argv = [exe, "mcp", "remove", "--scope", "user", NAME] if remove else [exe, "mcp", "add", "--scope", "user", NAME, "--", cmd, *args]
        proc = subprocess.run(argv, capture_output=True, text=True)
        ok = proc.returncode == 0
        out = (proc.stdout + proc.stderr).strip().splitlines()[-1:] or [""]
        if not ok and "already exists" in " ".join(out):
            return Result(client_id, "unchanged", None, "Already configured in Claude Code.")
        return Result(client_id, ("removed" if remove else "installed") if ok else "error", None, out[0])

    if client.fmt in ("yaml",) or (client.fmt == "jsonc" and path.exists() and _has_comments(path.read_text(encoding="utf-8"))):
        where = f"in {path}" if path else ""
        return Result(client_id, "manual", str(path),
                      f"This file can hold comments or YAML that an automatic edit could damage. Paste this {where}:\n{snippet(client, cmd, args)}")

    if client.fmt == "toml":
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        has = re.search(rf"^\[mcp_servers\.{NAME}\]\s*$", text, re.M)
        if remove:
            if not has:
                return Result(client_id, "unchanged", str(path), "Not configured.")
            new = re.sub(rf"^\[mcp_servers\.{NAME}\]\s*\n(?:(?!\[).*\n?)*", "", text, flags=re.M)
        else:
            if has:
                return Result(client_id, "unchanged", str(path), "Already configured. Edit the [mcp_servers.redress] section to change it.")
            new = text + ("" if not text or text.endswith("\n") else "\n") + ("\n" if text else "") + snippet(client, cmd, args)
        if dry_run:
            return Result(client_id, "manual", str(path), f"Would write {path}:\n{snippet(client, cmd, args)}")
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            _backup(path)
        path.write_text(new, encoding="utf-8")
        return Result(client_id, "removed" if remove else "installed", str(path), client.restart)

    # JSON (or JSONC without comments)
    data: dict = {}
    if path.exists():
        raw = path.read_text(encoding="utf-8").strip()
        if raw:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as e:
                return Result(client_id, "error", str(path), f"Not valid JSON ({e}); not touching it. Add this by hand:\n{snippet(client, cmd, args)}")
    if not isinstance(data, dict):
        return Result(client_id, "error", str(path), "Unexpected file shape; not touching it.")
    servers = data.get(client.key)
    if servers is not None and not isinstance(servers, dict):
        return Result(client_id, "error", str(path), f"'{client.key}' is not an object; not touching it.")
    servers = dict(servers or {})
    entry = client.entry(cmd, args)
    if remove:
        if NAME not in servers:
            return Result(client_id, "unchanged", str(path), "Not configured.")
        servers.pop(NAME)
        status = "removed"
    else:
        if servers.get(NAME) == entry:
            return Result(client_id, "unchanged", str(path), "Already configured.")
        status = "updated" if NAME in servers else "installed"
        servers[NAME] = entry
    data[client.key] = servers
    if dry_run:
        return Result(client_id, "manual", str(path), f"Would write {path}:\n{json.dumps({client.key: {NAME: entry}}, indent=2)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        _backup(path)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return Result(client_id, status, str(path), client.restart)


def detected_clients(home: Path | None = None) -> list[str]:
    home = home or Path.home()
    found = [c.id for c in CLIENTS.values() if c.detected(home)]
    if "claude-code" not in found and shutil.which("claude"):
        found.append("claude-code")
    return found


def main(args) -> int:
    cmd, cargs = server_command(args.source, args.read_only)
    if args.list or not (args.clients or args.all):
        found = set(detected_clients())
        print(f"Server command: {cmd} {' '.join(cargs)}\n")
        for c in CLIENTS.values():
            mark = "found" if c.id in found else "     "
            print(f"  [{mark}] {c.id:<15} {c.label}")
        print("\nInstall: redress install <client> [...]   or   redress install --all   (add --dry-run to preview)")
        return 0
    targets = detected_clients() if args.all else args.clients
    unknown = [t for t in targets if t not in CLIENTS]
    if unknown:
        print(f"Unknown client(s): {', '.join(unknown)}. Known: {', '.join(CLIENTS)}", file=sys.stderr)
        return 2
    code = 0
    for t in targets:
        r = install(t, cmd, cargs, dry_run=args.dry_run, remove=args.remove)
        print(f"{CLIENTS[t].label}: {r.status}{' (' + r.path + ')' if r.path else ''}")
        if r.message:
            print("  " + r.message.replace("\n", "\n  "))
        code = max(code, 1 if r.status == "error" else 0)
    return code


def setup(args) -> int:
    """Guided setup: find AI apps, show the planned changes, ask, apply with backups."""
    cmd, cargs = server_command(args.source, args.read_only)
    found = detected_clients()
    print("redress setup: connect redress to your AI apps\n")
    print(f"Server command: {cmd} {' '.join(cargs)}")
    if not found:
        print("\nNo supported AI apps were found. Manual setup for every app: "
              "https://github.com/alexgaoth/redress/blob/main/docs/clients.md")
        return 0
    targets = args.clients or found
    unknown = [t for t in targets if t not in CLIENTS]
    if unknown:
        print(f"Unknown app(s): {', '.join(unknown)}. Known: {', '.join(CLIENTS)}", file=sys.stderr)
        return 2
    interactive = sys.stdin.isatty() and not args.yes
    if interactive and not args.clients:
        print("\nFound:")
        for i, t in enumerate(found, 1):
            print(f"  {i}. {CLIENTS[t].label}")
        answer = input("\nAdd redress to which apps? [Enter = all, numbers like 1,3, or n to cancel] ").strip().lower()
        if answer in ("n", "no"):
            print("Cancelled. Nothing changed.")
            return 0
        if answer:
            try:
                targets = [found[int(x) - 1] for x in answer.replace(" ", "").split(",") if x]
            except (ValueError, IndexError):
                print("Did not understand that. Nothing changed.", file=sys.stderr)
                return 2
    print("\nPlanned changes:")
    for t in targets:
        r = install(t, cmd, cargs, dry_run=True, remove=args.remove)
        print(f"- {CLIENTS[t].label}: " + r.message.replace("\n", "\n    "))
    if not args.yes:
        if not interactive:
            print("\nRun again with --yes to apply.")
            return 0
        if input("\nApply these changes? Each config file is backed up first. [y/N] ").strip().lower() not in ("y", "yes"):
            print("Cancelled. Nothing changed.")
            return 0
    print()
    code, restart = 0, []
    for t in targets:
        r = install(t, cmd, cargs, remove=args.remove)
        print(f"{CLIENTS[t].label}: {r.status}{' (' + r.path + ')' if r.path else ''}")
        if r.status == "manual" and r.message:
            print("  " + r.message.replace("\n", "\n  "))
        if r.status in ("installed", "updated", "removed"):
            restart.append(CLIENTS[t].label)
        code = max(code, 1 if r.status == "error" else 0)
    if restart:
        print(f"\nRestart {', '.join(restart)}. Then ask your agent, for example:")
        print('  "My internet bill went up $25. Use redress to get it back down."')
        print('  "Is this text from USPS real? <paste the text>"')
    return code
