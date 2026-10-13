import datetime as dt

import pytest

from redress import advisor
from redress.advisor import NotFound


def test_company_playbook_resolves_channels_and_regulator(fixture_registry):
    pb = advisor.get_playbook(fixture_registry, "Example Air", "delayed_baggage", "ca", today=dt.date(2026, 10, 12))
    assert pb["playbook_source"] == "company"
    assert pb["steps"][1]["channel"]["id"] == "baggage-claim-form"
    assert pb["steps"][2]["regulator"]["id"] == "us-dot"
    assert any(f.get("kind") == "deadline" for f in pb["facts"])
    assert [r["id"] for r in pb["rules"]["in_force"]] == ["example-refund-rule"]
    assert pb["warnings"] == []


def test_generic_fallback_when_company_has_no_playbook(fixture_registry):
    pb = advisor.get_playbook(fixture_registry, "example-air", "lost_baggage", today=dt.date(2026, 10, 12))
    assert pb["playbook_source"] == "generic"
    assert pb["steps"][0]["do"].startswith("Keep the delayed-bag file open")
    assert any("No Example Air playbook" in w for w in pb["warnings"])
    # Channels with a matching purpose, or no purpose, are offered.
    assert {c["id"] for c in pb["channels"]} == {"baggage-claim-form", "reservations-phone"}


def test_stale_items_are_flagged(fixture_registry):
    pb = advisor.get_playbook(fixture_registry, "example-air", "delayed_baggage", today=dt.date(2028, 1, 1))
    assert pb["steps"][1]["channel"]["stale"] is True
    assert any("last verified" in w for w in pb["warnings"])


def test_unknown_issue_and_company(fixture_registry):
    with pytest.raises(NotFound, match="Unknown issue"):
        advisor.get_playbook(fixture_registry, "example-air", "nope")
    with pytest.raises(NotFound, match="No company matches"):
        advisor.get_playbook(fixture_registry, "acme widgets", "billing_error")


def test_escalation_resolves_state_agencies_and_payment_rules(fixture_registry):
    fixture_registry.companies["example-air"]["escalation"].append({"rung": "state_agency", "agency_kind": "attorney_general"})
    esc = advisor.get_escalation(fixture_registry, "example-air", "CA")
    rungs = [s["rung"] for s in esc["ladder"]]
    assert rungs == ["frontline", "written_complaint", "regulator", "payment_dispute", "state_agency"]
    assert esc["ladder"][-1]["agencies"][0]["id"] == "ca-ag"
    no_state = advisor.get_escalation(fixture_registry, "example-air")
    assert "Ask for the person's state" in no_state["ladder"][-1]["agencies"]


def test_find_regulators_filters_state_agencies_by_sector(fixture_registry):
    out = advisor.find_regulators(fixture_registry, "utility", "ca")
    assert {a["id"] for a in out["state"]} == {"ca-ag", "ca-puc"}
    out = advisor.find_regulators(fixture_registry, "airline", "ca")
    assert {a["id"] for a in out["state"]} == {"ca-ag"}


def test_rules_split_by_status(fixture_registry):
    fixture_registry.rules["example-refund-rule"]["status"] = "vacated"
    out = advisor.rules_for(fixture_registry, "airline", "flight_cancellation")
    assert out["in_force"] == []
    assert out["not_in_force"][0]["do_not_cite"].startswith("This rule is not in force")
    assert "points" not in out["not_in_force"][0]


def test_next_rung():
    ladder = [{"rung": "frontline"}, {"rung": "written_complaint"}, {"rung": "regulator"}]
    assert advisor.next_rung(ladder, [])["rung"] == "frontline"
    assert advisor.next_rung(ladder, ["frontline"])["rung"] == "written_complaint"
    assert advisor.next_rung(ladder, ["regulator"]) is None
