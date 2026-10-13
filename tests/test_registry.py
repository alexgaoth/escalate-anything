import copy
import datetime as dt
import shutil
from pathlib import Path

import yaml

from redress.registry import Registry, normalize

from .conftest import FIXTURES


def test_real_registry_is_valid():
    reg = Registry.load()
    problems = reg.validate()
    assert not problems, "\n".join(map(str, problems))


def test_fixture_registry_is_valid(fixture_registry):
    assert fixture_registry.validate() == []
    assert set(fixture_registry.companies) == {"example-air"}


def test_docs_example_matches_fixture():
    doc = (Path(__file__).parents[1] / "docs" / "authoring.md").read_text()
    fixture = (FIXTURES / "companies" / "airline" / "example-air.yaml").read_text()
    block = doc.split("## Company example\n\n```yaml\n", 1)[1].split("```", 1)[0]
    assert fixture.startswith(block)  # the fixture adds security data after the documented example


def test_dates_stay_strings(fixture_registry):
    ch = fixture_registry.companies["example-air"]["channels"][0]
    assert ch["last_verified"] == "2026-10-12"


def test_find_company_by_alias_and_fuzzy(fixture_registry):
    assert fixture_registry.find_company("ExampleAir")[0]["id"] == "example-air"
    assert fixture_registry.find_company("example airline")[0]["id"] == "example-air"
    assert fixture_registry.find_company("zzz") == []


def test_normalize():
    assert normalize("AT&T  Wireless!") == "at and t wireless"


def _write_company(tmp_path: Path, mutate) -> Registry:
    root = tmp_path / "registry"
    shutil.copytree(FIXTURES, root)
    path = root / "companies" / "airline" / "example-air.yaml"
    data = yaml.safe_load(path.read_text())
    data = copy.deepcopy(data)
    for ch in data["channels"]:
        ch["last_verified"] = str(ch["last_verified"])
    mutate(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    return Registry.load(root)


def _messages(reg: Registry) -> str:
    return "\n".join(map(str, reg.validate()))


def test_rejects_bad_phone(tmp_path):
    reg = _write_company(tmp_path, lambda d: d["channels"][2].update(value="1 (800) 555-0100"))
    assert "must look like +1-800-555-0100" in _messages(reg)


def test_rejects_unknown_issue_with_hint(tmp_path):
    reg = _write_company(tmp_path, lambda d: d["playbooks"][0].update(issue="delayed_bagage"))
    assert "did you mean 'delayed_baggage'" in _messages(reg)


def test_rejects_unknown_channel_reference(tmp_path):
    reg = _write_company(tmp_path, lambda d: d["escalation"].append({"rung": "executive", "channel": "nope"}))
    assert "unknown channel 'nope'" in _messages(reg)


def test_rejects_unknown_regulator(tmp_path):
    reg = _write_company(tmp_path, lambda d: d.update(regulators=["dot"]))
    assert "unknown regulator 'dot'" in _messages(reg)


def test_rejects_missing_source(tmp_path):
    reg = _write_company(tmp_path, lambda d: d["channels"][0].pop("source"))
    assert "'source' is a required property" in _messages(reg)


def test_rejects_future_date(tmp_path):
    future = (dt.date.today() + dt.timedelta(days=3)).isoformat()
    reg = _write_company(tmp_path, lambda d: d["channels"][0].update(last_verified=future))
    assert "is in the future" in _messages(reg)


def test_community_tip_needs_source(tmp_path):
    reg = _write_company(tmp_path, lambda d: d["tips"][0].pop("source"))
    assert "community tip needs a source" in _messages(reg)


def test_stale(fixture_registry):
    rows = fixture_registry.stale(days=30, today=dt.date(2026, 10, 12))
    assert any(rel.endswith("example-refund-rule.yaml") for rel, _, _ in rows)
    assert not any(rel.endswith("example-air.yaml") for rel, _, _ in rows)


def test_export_contains_everything(fixture_registry):
    out = fixture_registry.export()
    assert [c["id"] for c in out["companies"]] == ["example-air"]
    assert out["states"][0]["id"] == "ca"


def test_schema_shapes():
    import json

    from redress.registry import SCHEMA_PATH

    defs = json.loads(SCHEMA_PATH.read_text())["$defs"]
    assert set(defs["rung"]["properties"]) == {"rung", "channel", "regulator", "agency_kind", "note"}
    assert set(defs["security"]["properties"]) == {"never_asks", "known_scams", "report_phishing"}
    assert "security" in defs["company"]["properties"]
