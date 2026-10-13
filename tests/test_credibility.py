import datetime as dt

from escalate_anything import advisor
from escalate_anything.credibility import classify, company_credibility, registry_credibility, verification_signal


def test_classify_tiers():
    own = {"example.com"}
    assert classify("https://www.example.com/contact", own) == "primary"
    assert classify("https://help.example.com/x", own) == "primary"
    assert classify("https://www.consumerfinance.gov/x", own) == "primary"
    assert classify("https://www.finra.org/x", own) == "primary"
    assert classify("https://www.law.cornell.edu/cfr", own) == "reference"
    assert classify("https://www.reuters.com/a", own) == "reference"
    assert classify("https://www.other-co.com/a", own, {"other-co.com"}) == "reference"
    assert classify("https://www.reddit.com/r/x", own) == "community"
    assert classify("https://web.archive.org/web/2026/https://example.com", own) == "archive"
    assert classify("https://random-blog.net/post", own) == "other"


def test_verification_signal():
    assert verification_signal({"source": "https://a.com", "notes": "Seen in a search snippet only."}) == "search_snippet"
    assert verification_signal({"source": "https://web.archive.org/web/1/https://a.com"}) == "archive"
    assert verification_signal({"source": "https://a.com", "verified_via": "browser"}) == "browser"
    assert verification_signal({"source": "https://a.com", "claim": "Plain fact."}) == "page"


def test_company_credibility_on_fixture(fixture_registry):
    c = fixture_registry.companies["example-air"]
    cc = company_credibility(fixture_registry, c, today=dt.date(2026, 10, 13))
    assert cc["grade"] in {"A", "B", "C"}
    assert cc["last_verified"] == "2026-10-12"
    assert cc["dossier_last_verified"] == "2026-10-01"
    assert cc["sources"]["primary"] >= 1 and cc["sources"]["community"] == 1  # the reddit link in the dossier
    assert "Grade" in cc["explanation"]
    later = company_credibility(fixture_registry, c, today=dt.date(2027, 10, 13))
    assert later["stale_items"] > 0 and later["grade"] != "A"


def test_credibility_reaches_tools(fixture_registry):
    pb = advisor.get_playbook(fixture_registry, "example-air", "delayed_baggage")
    assert pb["credibility"]["last_verified"]
    summary = advisor.company_summary(fixture_registry, fixture_registry.companies["example-air"])
    assert summary["credibility"] in {"A", "B", "C"} and summary["last_verified"]
    assert registry_credibility(fixture_registry)["grades"]
