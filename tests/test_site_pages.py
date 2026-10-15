"""The static HTML pages: one per playbook, company, issue and guide, plus sitemap.xml and robots.txt."""

import re
import xml.etree.ElementTree as ET
from html import unescape
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import pytest

from escalate_anything.pages import render_markdown, tel_href
from escalate_anything.registry import Registry
from escalate_anything.site import BASE_URL, build_site

SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


def _pages(out: Path) -> list[Path]:
    return sorted(out.rglob("index.html"))


def _url(out: Path, page: Path) -> str:
    rel = page.parent.relative_to(out).as_posix()
    return BASE_URL + ("" if rel == "." else rel + "/")


def _title(html: str) -> str:
    return unescape(re.search(r"<title>(.*?)</title>", html, re.S).group(1))


@pytest.fixture(scope="module")
def real_site(tmp_path_factory) -> tuple[Path, Registry]:
    out = tmp_path_factory.mktemp("site")
    reg = Registry.load()
    build_site(out, reg)
    return out, reg


# ---- the real registry -------------------------------------------------------


def test_one_page_per_playbook(real_site):
    out, reg = real_site
    expected = {f"c/{c['id']}/{pb['issue'].replace('_', '-')}"
                for c in reg.companies.values() for pb in c.get("playbooks", [])}
    found = {p.parent.relative_to(out).as_posix() for p in (out / "c").glob("*/*/index.html")}
    assert found == expected
    assert len(found) == reg.stats()["playbooks"]
    assert {p.parent.name for p in (out / "c").glob("*/index.html")} == set(reg.companies)
    assert {p.parent.name for p in (out / "issues").glob("*/index.html")} == {i.replace("_", "-") for i in reg.issues}
    assert {p.parent.name for p in (out / "guides").glob("*/index.html")} == set(reg.guides)
    assert (out / "guides" / "airline.md").is_file()  # the Markdown files stay


def test_united_delayed_bag_page(real_site):
    out, _ = real_site
    html = (out / "c" / "united-airlines" / "delayed-baggage" / "index.html").read_text()
    assert "<h1>United Airlines: delayed bag</h1>" in html
    assert "Report the bag within 24 hours of arrival" in html  # the deadline line
    assert 'href="https://www.united.com/en/us/baggage/bag-help"' in html  # a fact's source
    assert 'href="tel:+18003352247"' in html  # Baggage Recovery Center
    assert "Let your AI agent handle this" in html and "uvx escalate-anything setup" in html
    assert "United Airlines lost my bag on [date and flight]. Use Escalate Anything to get me reimbursed." in html
    assert "U.S. Department of Transportation" in html  # the regulator rung
    assert 'href="../../../c/united-airlines/#dossier"' in html
    assert "/issues/new?template=data-correction.yml&amp;company=united-airlines" in html
    assert "Not legal advice" in html and "CC BY 4.0" in html
    assert '<link rel="canonical" href="https://escalate.alexgaoth.com/c/united-airlines/delayed-baggage/">' in html


def test_titles_descriptions_and_canonicals(real_site):
    out, _ = real_site
    titles = []
    for page in _pages(out):
        html = page.read_text()
        canonical = re.search(r'<link rel="canonical" href="([^"]+)">', html)
        assert canonical and canonical.group(1) == _url(out, page), page
        assert '<html lang="en">' in html
        if page == out / "index.html":
            continue
        title = _title(html)
        desc = unescape(re.search(r'<meta name="description" content="([^"]*)">', html).group(1))
        assert len(title) <= 65 and 0 < len(desc) <= 160, page
        titles.append(title)
        assert '"@type":"BreadcrumbList"' in html and 'aria-label="Breadcrumb"' in html
        assert 'property="og:image"' in html and 'name="twitter:card"' in html
        # No JavaScript: the only script is the JSON-LD block.
        assert re.findall(r"<script\b[^>]*>", html) == ['<script type="application/ld+json">']
    assert len(titles) == len(set(titles)), "page titles must be unique"


def test_sitemap_lists_every_page(real_site):
    out, _ = real_site
    root = ET.parse(out / "sitemap.xml").getroot()
    urls = root.findall(f"{SITEMAP_NS}url")
    locs = [u.findtext(f"{SITEMAP_NS}loc") for u in urls]
    pages = _pages(out)
    assert len(locs) == len(pages) == len(set(locs))
    assert set(locs) == {_url(out, p) for p in pages}
    by_loc = {u.findtext(f"{SITEMAP_NS}loc"): u.findtext(f"{SITEMAP_NS}lastmod") for u in urls}
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", by_loc[BASE_URL + "c/united-airlines/delayed-baggage/"])
    assert by_loc[BASE_URL] == max(v for v in by_loc.values() if v)
    assert (out / "robots.txt").read_text().strip().endswith(f"Sitemap: {BASE_URL}sitemap.xml")


def test_relative_links_resolve(real_site):
    out, _ = real_site
    missing = set()
    for page in _pages(out)[::7] + [out / "c" / "united-airlines" / "delayed-baggage" / "index.html"]:
        base = _url(out, page)
        for href in re.findall(r'href="([^"]+)"', page.read_text()):
            full = urljoin(base, unescape(href))
            if not full.startswith(BASE_URL):
                continue
            path = urlsplit(full).path[len(urlsplit(BASE_URL).path):]
            target = out / path / "index.html" if path == "" or path.endswith("/") else out / path
            if not target.exists():
                missing.add(f"{page.relative_to(out)} -> {href}")
    assert not missing, sorted(missing)[:10]


def test_llms_txt_links_the_pages(real_site):
    out, _ = real_site
    text = (out / "llms.txt").read_text()
    assert f"[HTML]({BASE_URL}c/united-airlines/)" in text
    assert f"[Delayed bag]({BASE_URL}issues/delayed-baggage/)" in text
    assert f"([HTML]({BASE_URL}guides/scams/))" in text
    assert f"{BASE_URL}companies/united-airlines.json" in text  # the JSON links stay


# ---- the fixture registry ----------------------------------------------------


def test_fixture_pages(tmp_path, fixture_registry):
    build_site(tmp_path, fixture_registry)
    pb = (tmp_path / "c" / "example-air" / "delayed-baggage" / "index.html").read_text()
    assert "Expense claims for a delayed bag must be submitted within 21 days" in pb
    assert 'href="https://www.example.com/legal/contract-of-carriage"' in pb
    assert 'href="../../../assets/pages.css"' in pb
    company = (tmp_path / "c" / "example-air" / "index.html").read_text()
    assert 'href="../../c/example-air/delayed-baggage/"' in company
    assert 'id="dossier"' in company and '<span class="badge warn">Reported by customers</span>' in company
    hub = (tmp_path / "issues" / "delayed-baggage" / "index.html").read_text()
    assert 'href="../../c/example-air/delayed-baggage/"' in hub
    guide = (tmp_path / "guides" / "airline" / "index.html").read_text()
    assert "<h2>Your leverage</h2>" in guide and 'href="../../c/example-air/"' in guide
    css = (tmp_path / "assets" / "pages.css").read_text()
    assert "--accent:" in css and "prefers-color-scheme: dark" in css
    index = (tmp_path / "index.html").read_text()
    assert '<a href="c/example-air/">Example Air</a>' in index  # the noscript list


def test_html_escaping(tmp_path, fixture_registry):
    c = fixture_registry.companies["example-air"]
    c["name"] = "Example <Air> & Co"
    c["playbooks"][0]["summary"] = 'Report it <script>alert(1)</script> & "claim"'
    c["known_blockers"] = ["Use <b>this</b> & that"]
    build_site(tmp_path, fixture_registry)
    for rel in ("c/example-air/delayed-baggage/index.html", "c/example-air/index.html", "issues/delayed-baggage/index.html"):
        html = (tmp_path / rel).read_text()
        assert "Example <Air>" not in html and "<script>alert" not in html and "<b>this" not in html, rel
        assert "Example &lt;Air&gt; &amp; Co" in html, rel
    pb = (tmp_path / "c/example-air/delayed-baggage/index.html").read_text()
    assert "Report it &lt;script&gt;alert(1)&lt;/script&gt; &amp; &quot;claim&quot;" in pb
    assert "Use &lt;b&gt;this&lt;/b&gt; &amp; that" in pb
    # The JSON-LD block cannot be closed early.
    ld = re.search(r'<script type="application/ld\+json">(.*?)</script>', pb, re.S).group(1)
    assert "<" not in ld and "Example \\u003cAir> & Co" in ld
    ET.parse(tmp_path / "sitemap.xml")


HOSTILE = """## In short <script>alert(1)</script>

Plain <img src=x onerror=alert(1)> text with **bold**, `code` and a [good link](https://example.com/a?b=1&c="2").

- A bullet with [bad link](javascript:alert(3)) and [data](data:text/html,<b>x</b>).
- [quote break](https://x.com/"onmouseover="alert(4)) and <a href="https://evil.example">raw anchor</a>
<!-- a hidden note <script>alert(5)</script> -->

### Sub **heading**
"""


def test_markdown_renderer_escapes_html():
    out = render_markdown(HOSTILE, 2)
    assert "<script" not in out.lower() and "<img" not in out and "<b>" not in out
    assert "javascript:" not in out and "data:" not in out and "hidden note" not in out
    assert not re.search(r"<[^>]*\son\w+\s*=", out)
    assert set(re.findall(r"</?([a-z0-9]+)", out)) <= {"h2", "h3", "p", "ul", "li", "strong", "code", "a"}
    assert '<a href="https://example.com/a?b=1&amp;c=&quot;2&quot;">good link</a>' in out
    assert "&lt;a href=&quot;https://evil.example&quot;&gt;raw anchor&lt;/a&gt;" in out
    assert "<strong>bold</strong>" in out and "<code>code</code>" in out
    assert "<h2>In short &lt;script&gt;alert(1)&lt;/script&gt;</h2>" in out
    assert "<h3>Sub <strong>heading</strong></h3>" in out


def test_tel_links():
    assert tel_href("+1-800-864-8331") == "tel:+18008648331"
    assert tel_href("+1-800-438-6744 ext. 70355") == "tel:+18004386744,70355"
