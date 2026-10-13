"""Keep an installed copy's data current: download the latest registry from GitHub.

The registry changes weekly (fixes from contributors and the refresh routine). Installed copies
(`uvx redress-mcp`) fetch the latest `registry/` folder from the repository, validate it with
the installed code, and only then swap it in. A source checkout uses `git pull` instead.

Privacy: this downloads a public archive from GitHub. It sends nothing about you or your cases.
Set REDRESS_OFFLINE=1 to turn it off.
"""

from __future__ import annotations

import datetime as dt
import io
import json
import os
import shutil
import tarfile
import tempfile
import threading
from pathlib import Path

import httpx

ARCHIVE_URL = "https://codeload.github.com/alexgaoth/redress/tar.gz/refs/heads/main"
MAX_AGE_DAYS = 7


def home() -> Path:
    return Path(os.environ.get("REDRESS_HOME", Path.home() / ".redress"))


def downloaded_registry() -> Path:
    return home() / "registry"


def _stamp_path() -> Path:
    return home() / "registry.json.meta"


def offline() -> bool:
    return os.environ.get("REDRESS_OFFLINE", "").lower() in ("1", "true", "yes")


def status() -> dict:
    meta = {}
    if _stamp_path().exists():
        try:
            meta = json.loads(_stamp_path().read_text())
        except json.JSONDecodeError:
            meta = {}
    return {"path": str(downloaded_registry()), "present": (downloaded_registry() / "sectors.yaml").exists(), **meta}


def is_due(today: dt.date | None = None) -> bool:
    today = today or dt.date.today()
    fetched = status().get("fetched")
    if not fetched:
        return True
    try:
        return (today - dt.date.fromisoformat(fetched[:10])).days >= MAX_AGE_DAYS
    except ValueError:
        return True


def update(url: str = ARCHIVE_URL, timeout: float = 60.0) -> dict:
    """Download, extract registry/, validate with the installed code, then swap atomically."""
    from .registry import Registry

    resp = httpx.get(url, timeout=timeout, follow_redirects=True)
    resp.raise_for_status()
    home().mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=home()) as tmp:
        tmp_root = Path(tmp)
        with tarfile.open(fileobj=io.BytesIO(resp.content), mode="r:gz") as tar:
            members = []
            for m in tar.getmembers():
                parts = Path(m.name).parts
                # Only regular files and directories under <top>/registry/, no links or absolute paths.
                if len(parts) < 2 or parts[1] != "registry" or not (m.isfile() or m.isdir()):
                    continue
                if m.name.startswith("/") or ".." in parts:
                    continue
                m.name = str(Path(*parts[1:]))
                members.append(m)
            tar.extractall(tmp_root, members=members, filter="data")
        new = tmp_root / "registry"
        if not (new / "sectors.yaml").exists():
            raise RuntimeError("the download has no registry/ folder")
        problems = Registry.load(new).validate()
        if problems:
            raise RuntimeError(
                f"the latest registry has {len(problems)} problem(s) with this version of redress "
                f"(first: {problems[0]}). Upgrade with: uvx redress-mcp@latest")
        target = downloaded_registry()
        old = home() / "registry.old"
        if old.exists():
            shutil.rmtree(old)
        if target.exists():
            target.rename(old)
        new.rename(target)
        if old.exists():
            shutil.rmtree(old)
    stats = Registry.load(downloaded_registry()).stats()
    meta = {"fetched": dt.datetime.now().isoformat(timespec="seconds"), "source": url,
            "companies": stats["companies"], "last_verified": stats["credibility"]["last_verified"]}
    _stamp_path().write_text(json.dumps(meta, indent=1))
    return {**status(), **meta}


def update_in_background_if_due() -> None:
    """Called at server start in installed copies. Never blocks, never raises."""
    if offline() or not is_due():
        return

    def run():
        try:
            update()
        except Exception:  # offline, rate-limited, or incompatible: keep the current data
            pass

    threading.Thread(target=run, name="redress-update", daemon=True).start()
