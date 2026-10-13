import json
import re
import shutil
import subprocess

import pytest

from escalate_anything.cli import main
from escalate_anything.registry import Registry
from escalate_anything.site import WEB_DIR, build_site, index_html

from .conftest import FIXTURES

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node is not installed")

# Loads the DOM-free core of app.js (it exports itself when `module` exists) and runs a list of calls.
JS_RUNNER = r"""
const fs = require("fs");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const mod = { exports: {} };
new Function("module", fs.readFileSync(input.app, "utf8"))(mod);
const core = mod.exports;
process.stdout.write(JSON.stringify(input.calls.map(([fn, ...args]) => core[fn](...args))));
"""


def _js(calls: list) -> list:
    payload = json.dumps({"app": str(WEB_DIR / "app.js"), "calls": calls})
    proc = subprocess.run([NODE, "-e", JS_RUNNER], input=payload, capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _embedded_data(html: str) -> dict:
    m = re.search(r'<script type="application/json" id="data">(.*?)</script>', html, re.S)
    assert m, "index.html has no embedded data blob"
    return json.loads(m.group(1))


def _fixture_copy(tmp_path, name="registry"):
    root = tmp_path / name
    shutil.copytree(FIXTURES, root)
    return root


def test_build_writes_every_file(tmp_path, fixture_registry):
    counts = build_site(tmp_path, fixture_registry)
    assert counts == {"companies": 1, "states": 1, "issues": len(fixture_registry.issues), "dossiers": 1, "guides": 2}
    for rel in ["index.html", "registry.json", "companies.json", "companies/example-air.json",
                "issues.json", "states/ca.json", "llms.txt", ".nojekyll",
                "dossiers/example-air.md", "guides/airline.md", "guides/scams.md"]:
        assert (tmp_path / rel).is_file(), rel
    assert (tmp_path / "guides" / "scams.md").read_text() == (FIXTURES / "guides" / "scams.md").read_text()


def test_company_json_has_scam_warnings_dossier_and_guide(tmp_path, fixture_registry):
    build_site(tmp_path, fixture_registry)
    doc = json.loads((tmp_path / "companies" / "example-air.json").read_text())
    assert doc["security"]["official_domains"] == ["example.com"]
    assert doc["security"]["never_asks"][0]["claim"].startswith("Example Air never asks")
    assert doc["security"]["report_phishing"][0]["value"] == "phishing@example.com"
    assert doc["dossier"]["markdown"].startswith("## In short")
    assert doc["dossier"]["last_verified"] == "2026-10-01" and doc["dossier"]["file"] == "dossiers/example-air.md"
    assert doc["guide"]["key"] == "airline" and doc["guide"]["page"].endswith("#/guides/airline")
    data = _embedded_data((tmp_path / "index.html").read_text())
    assert [g["key"] for g in data["guides"]] == ["scams", "airline"]
    assert data["dossiers"] == ["example-air"]


def test_build_without_dossiers_guides_or_security(tmp_path):
    root = _fixture_copy(tmp_path)
    shutil.rmtree(root / "dossiers")
    shutil.rmtree(root / "guides")
    path = root / "companies" / "airline" / "example-air.yaml"
    path.write_text(path.read_text().split("\nofficial_domains:")[0] + "\n")
    out = tmp_path / "site"
    counts = build_site(out, Registry.load(root))
    assert counts["dossiers"] == 0 and counts["guides"] == 0
    doc = json.loads((out / "companies" / "example-air.json").read_text())
    assert doc["dossier"] is None and doc["guide"] is None
    assert not any(doc["security"].values())
    assert _embedded_data((out / "index.html").read_text())["guides"] == []
    assert list((out / "guides").iterdir()) == []
    assert "## Guides" not in (out / "llms.txt").read_text()


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
    assert text.startswith("# Escalate Anything\n\n> ")
    assert "- [Example Air](https://intro.alexgaoth.com/escalate-anything/companies/example-air.json)" in text
    assert "approves every message" in text
    assert "[California](https://intro.alexgaoth.com/escalate-anything/states/ca.json)" in text
    assert "`security` field" in text
    assert "- [Common scams](https://intro.alexgaoth.com/escalate-anything/guides/scams.md)" in text
    assert "[dossier](https://intro.alexgaoth.com/escalate-anything/dossiers/example-air.md)" in text


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


def test_contact_checker_is_gone(tmp_path, fixture_registry):
    build_site(tmp_path, fixture_registry)
    assert not (tmp_path / "contacts.json").exists()
    assert not (tmp_path / "red_flags.json").exists()
    html = (tmp_path / "index.html").read_text()
    nav = re.search(r'<nav class="nav"[^>]*>(.*?)</nav>', html, re.S)
    assert nav and 'href="#/guides/scams"' in nav.group(1)
    assert "#/check" not in nav.group(1)
    assert "#/check" not in html and "contacts.json" not in html and "red_flags.json" not in html
    text = (tmp_path / "llms.txt").read_text()
    assert "contacts.json" not in text and "red_flags.json" not in text and "#/check" not in text


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


# ---- the JavaScript in app.js (run with node) ---------------------------------

HOSTILE_DOSSIER = """---
company: example-air
title: Example Air
last_verified: 2026-10-01
---

## In short <script>alert(1)</script>

Plain <img src=x onerror=alert(1)> text with **bold** and a [good link](https://example.com/a?b=1&c="2").

- A bullet with <script>alert(2)</script> and [bad link](javascript:alert(3)) and [data](data:text/html,<b>x</b>).
- [quote break](https://x.com/"onmouseover="alert(4)) and <a href="https://evil.example">raw anchor</a>
<!-- a hidden note <script>alert(5)</script> -->

### Sub **heading**
"""


@needs_node
def test_markdown_renderer_escapes_html(tmp_path):
    root = _fixture_copy(tmp_path)
    (root / "dossiers" / "example-air.md").write_text(HOSTILE_DOSSIER)
    build_site(tmp_path / "site", Registry.load(root))
    markdown = json.loads((tmp_path / "site" / "companies" / "example-air.json").read_text())["dossier"]["markdown"]
    assert "<script>" in markdown  # stored as written; the page escapes it
    [body] = _js([["stripFrontMatter", HOSTILE_DOSSIER]])
    html, guide = _js([["renderMarkdown", markdown, 3], ["renderMarkdown", body, 2]])
    for out in (html, guide):
        assert "<script" not in out.lower()
        assert "<img" not in out and "<b>" not in out
        assert "javascript:" not in out and "data:" not in out
        assert not re.search(r"<[^>]*\son\w+\s*=", out), "an event handler attribute got through"
        assert set(re.findall(r"</?([a-z0-9]+)", out)) <= {"h2", "h3", "h4", "p", "ul", "li", "strong", "a"}
        assert "hidden note" not in out
        assert '<a href="https://example.com/a?b=1&amp;c=&quot;2&quot;" target="_blank" rel="noopener noreferrer">good link</a>' in out
        assert "&lt;a href=&quot;https://evil.example&quot;&gt;raw anchor&lt;/a&gt;" in out
        assert "<strong>bold</strong>" in out
        assert "bad link" in out and "<li>" in out
    assert "<h3>In short &lt;script&gt;alert(1)&lt;/script&gt;</h3>" in html
    assert "<h4>Sub <strong>heading</strong></h4>" in html
    assert "<h2>In short" in guide and "<h3>Sub" in guide


@needs_node
def test_front_matter_is_stripped_like_python(fixture_registry):
    text = (FIXTURES / "guides" / "airline.md").read_text()
    [body, plain] = _js([["stripFrontMatter", text], ["stripFrontMatter", "## No front matter\n"]])
    assert body.strip() == fixture_registry.guides["airline"].body.strip()
    assert plain == "## No front matter\n"


def test_badges_are_written(fixture_registry, tmp_path):
    import json

    from escalate_anything.site import build_site

    build_site(tmp_path / "out", fixture_registry)
    b = json.loads((tmp_path / "out" / "badges" / "companies.json").read_text())
    assert b == {"schemaVersion": 1, "label": "companies", "message": "1", "color": "2ea44f"}
    assert json.loads((tmp_path / "out" / "badges" / "verified.json").read_text())["message"] == "2026-10-12"
