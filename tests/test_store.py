import datetime as dt

import pytest

from redress.store import Store, StoreError


@pytest.fixture
def db(tmp_path):
    return Store(tmp_path / "t.db")


def test_case_timeline_and_follow_up(db):
    case = db.open_case("example-air", "delayed_baggage", "Bag missing after ORD-SFO", "Reimburse $180", 180.0, "CA", "1234")
    cid = case["id"]
    db.log_event(cid, "contact", "Reported at SFO baggage office", "2026-10-01", rung="frontline", reference="SFOUA12345")
    case = db.log_event(cid, "promise", "Agent said the bag arrives tomorrow", "2026-10-01", rep_name="Dana",
                        promised="Bag delivered by 2026-10-02", follow_up_on="2026-10-03")
    assert case["rungs_used"] == ["frontline"]
    assert case["references"][0]["reference"] == "SFOUA12345"
    assert case["promises"][0]["by"] == "Dana"
    assert case["follow_up"]["on"] == "2026-10-03"
    assert db.followups_due("2026-10-02") == []
    assert db.followups_due("2026-10-03")[0]["case_id"] == cid
    db.log_event(cid, "response", "Bag delivered", "2026-10-03")
    assert db.followups_due("2026-12-31") == []


def test_refuses_card_numbers_and_ssn_but_allows_tracking_numbers(db):
    with pytest.raises(StoreError, match="card number"):
        db.open_case("x", "billing_error", "my card is 4111 1111 1111 1111")
    with pytest.raises(StoreError, match="SSN"):
        db.open_case("x", "billing_error", "ssn 123-45-6789")
    with pytest.raises(StoreError, match="last 4"):
        db.open_case("x", "billing_error", "s", account_hint="123456")
    cid = db.open_case("x", "lost_package", "package")["id"]
    db.log_event(cid, "reference", "FedEx tracking", reference="4111111111111111")  # Luhn-valid digits in a reference are allowed
    db.log_event(cid, "note", "order 1234567890123 shipped")  # 13 digits, not Luhn-valid


def test_validation_errors(db):
    cid = db.open_case("x", "billing_error", "s")["id"]
    with pytest.raises(StoreError, match="kind must be"):
        db.log_event(cid, "phonecall", "x")
    with pytest.raises(StoreError, match="YYYY-MM-DD"):
        db.log_event(cid, "note", "x", follow_up_on="next week")
    db.close_case(cid, "resolved", 50.0, "Written complaint form")
    with pytest.raises(StoreError, match="closed"):
        db.log_event(cid, "note", "x")
    assert db.outcome_stats()[0]["recovered"] == 50.0


def test_bill_check_increase_and_promo(db):
    for month, amount in [("2026-06-30", 80), ("2026-07-31", 80), ("2026-08-31", 82), ("2026-09-30", 105)]:
        db.record_bill("comcast-xfinity", month, amount, promo_end="2026-11-01" if month == "2026-09-30" else None)
    findings = db.check_bills(today=dt.date(2026, 10, 12))
    kinds = {f["kind"]: f for f in findings}
    assert kinds["increase"]["increase"] == 25.0
    assert kinds["increase"]["baseline"] == 80
    assert kinds["promo_ending"]["days"] == 20


def test_bill_check_ignores_small_changes(db):
    for month, amount in [("2026-07-31", 30), ("2026-08-31", 30), ("2026-09-30", 32)]:
        db.record_bill("netflix", month, amount)
    assert db.check_bills(today=dt.date(2026, 10, 12)) == []


def test_record_bill_upserts(db):
    db.record_bill("netflix", "2026-09-30", 15.49)
    db.record_bill("netflix", "2026-09-30", 17.99)
    assert [b["amount"] for b in db.bills("netflix")] == [17.99]
