import json
import re

from redress.cli import main
from redress.site import build_site, index_html


def _embedded_data(html: str) -> dict:
    m = re.search(r'<script type="application/json" id="data">(.*?)</script>', html, re.S)
    assert m, "index.html has no embedded data blob"
    return json.loads(m.group(1))


def test_build_writes_every_file(tmp_path, fixture_registry):
    counts = build_site(tmp_path, fixture_registry)
    assert counts == {"companies": 1, "states": 1, "issues": len(fixture_registry.issues)}
    for rel in ["index.html", "registry.json", "companies.json", "companies/example-air.json",
                "issues.json", "states/ca.json", "llms.txt", ".nojekyll"]:
        assert (tmp_path / rel).is_file(), rel


def test_json_files_parse(tmp_path, fixture_registry):
    build_site(tmp_path, fixture_registry)
    registry = json.loads((tmp_path / "registry.json").read_text())
    assert [c["id"] for c in registry["companies"]] == ["example-air"]

    doc = json.loads((tmp_path / "companies" / "example-air.json").read_text())
    assert doc["company"]["id"] == "example-air"
    assert set(doc["playbooks"]) == {"delayed_baggage"}
    pb = doc["playbooks"]["delayed_baggage"]
    assert pb["playbook_source"] == "company"
    assert pb["steps"][1]["channel"]["id"] == "baggage-claim-form"
    assert [r["rung"] for r in doc["escalation"]] == ["frontline", "written_complaint", "regulator", "payment_dispute"]

    issues = json.loads((tmp_path / "issues.json").read_text())
    assert next(i for i in issues if i["id"] == "delayed_baggage")["companies"] == ["example-air"]
    assert json.loads((tmp_path / "companies.json").read_text())[0]["id"] == "example-air"
    assert json.loads((tmp_path / "states" / "ca.json").read_text())["id"] == "ca"


def test_llms_txt_lists_the_company(tmp_path, fixture_registry):
    build_site(tmp_path, fixture_registry)
    text = (tmp_path / "llms.txt").read_text()
    assert text.startswith("# redress\n\n> ")
    assert "- [Example Air](https://alexgaoth.github.io/redress/companies/example-air.json)" in text
    assert "approves every message" in text
    assert "[California](https://alexgaoth.github.io/redress/states/ca.json)" in text


def test_index_html_is_self_contained(tmp_path, fixture_registry):
    build_site(tmp_path, fixture_registry)
    html = (tmp_path / "index.html").read_text()
    assert not re.search(r"<script\b[^>]*\bsrc\s*=\s*[\"']?(https?:)?//", html, re.I)
    for tag in re.findall(r"<link\b[^>]*>", html, re.I):
        if re.search(r"\brel\s*=\s*[\"']?[^\"'>]*(stylesheet|preload|modulepreload)", tag, re.I):
            assert not re.search(r"\bhref\s*=\s*[\"']?(https?:)?//", tag, re.I), tag
    assert not re.search(r"@import|url\(\s*[\"']?(https?:)?//", html, re.I)
    assert not re.search(r"__[A-Z]+__", html), "a template token was not replaced"
    data = _embedded_data(html)
    assert [c["id"] for c in data["companies"]] == ["example-air"]
    assert data["stats"]["companies"] == 1


def test_embedded_data_cannot_close_the_script(fixture_registry):
    fixture_registry.companies["example-air"]["name"] = "Example </script><script>alert(1)</script>"
    html = index_html(fixture_registry)
    assert "</script><script>alert(1)" not in html
    assert _embedded_data(html)["companies"][0]["name"].startswith("Example </script>")


def test_site_command_builds_the_real_registry(tmp_path):
    assert main(["site", "-o", str(tmp_path)]) == 0
    doc = json.loads((tmp_path / "companies" / "united-airlines.json").read_text())
    assert doc["playbooks"]
    assert "companies/united-airlines.json" in (tmp_path / "llms.txt").read_text()
