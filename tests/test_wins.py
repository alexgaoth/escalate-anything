from escalate_anything.registry import Registry
from escalate_anything.store import Store
from escalate_anything.wins import case_story


def test_case_story_leaves_out_references_and_names(tmp_path):
    db = Store(tmp_path / "t.db")
    case = db.open_case("united-airlines", "delayed_baggage", "Bag delayed 3 days on ORD-SFO, file ORD12345M")
    db.log_event(case["id"], "contact", "Reported at the airport, file ORD12345M", occurred_on="2026-09-02",
                 rung="frontline", channel="airport desk", reference="ORD12345M", rep_name="Dana")
    db.log_event(case["id"], "escalation", "Filed DOT complaint", occurred_on="2026-09-10", rung="regulator")
    db.close_case(case["id"], "resolved", amount_recovered=212.5, what_worked="DOT complaint with receipts")
    story = case_story(db.get_case(case["id"]), Registry.load())

    assert story.startswith("# United Airlines: ")
    assert "$212.50" in story and "DOT complaint with receipts" in story
    assert "2026-09-02" in story and "regulator" in story
    assert "ORD12345M" not in story and "Dana" not in story
    assert "c/united-airlines/delayed-baggage/" in story
