import io
import shutil
import tarfile
from pathlib import Path

import httpx
import pytest

from escalate_anything import updater

from .conftest import FIXTURES


def _archive(registry_dir: Path, extra: dict[str, bytes] | None = None) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(registry_dir, arcname="escalate-anything-main/registry")
        for name, data in (extra or {}).items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("ESCALATE_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


def _serve(monkeypatch, payload: bytes):
    real_get = httpx.get

    def fake_get(url, **kw):
        return httpx.Response(200, content=payload, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    return real_get


def test_update_extracts_only_registry_and_validates(home, monkeypatch):
    payload = _archive(FIXTURES, {"escalate-anything-main/src/evil.py": b"print(1)", "escalate-anything-main/registry/../../escape.txt": b"x"})
    _serve(monkeypatch, payload)
    meta = updater.update(url="https://example.invalid/archive.tgz")
    assert (home / "registry" / "sectors.yaml").exists()
    assert not (home / "src").exists() and not (home.parent / "escape.txt").exists()
    assert meta["companies"] == 1 and meta["fetched"]
    assert updater.status()["present"] is True
    assert updater.is_due() is False


def test_update_refuses_invalid_data(home, monkeypatch, tmp_path):
    bad = tmp_path / "bad"
    shutil.copytree(FIXTURES, bad)
    p = bad / "companies" / "airline" / "example-air.yaml"
    p.write_text(p.read_text().replace("sector: airline", "sector: spaceline"))
    _serve(monkeypatch, _archive(bad))
    with pytest.raises(RuntimeError, match="problem"):
        updater.update(url="https://example.invalid/archive.tgz")
    assert not (home / "registry").exists()


def test_offline_flag(monkeypatch):
    monkeypatch.setenv("ESCALATE_OFFLINE", "1")
    assert updater.offline() is True


def test_freshness_report_and_worklist(fixture_registry):
    import datetime as dt

    from escalate_anything import freshness

    links = [{"url": "https://www.example.com/gone", "status": "dead", "code": 404, "used_by": ["example-air.channels[0].value"]}]
    rep = freshness.build(fixture_registry, links, days=30, today=dt.date(2027, 1, 1))
    md = freshness.markdown(rep)
    assert "## Dead links (1)" in md and "https://www.example.com/gone" in md
    assert "Not verified in 180+ days" in md
    wl = freshness.worklist(rep, 3)
    assert wl[0]["kind"] == "dead_link" and len(wl) == 3
