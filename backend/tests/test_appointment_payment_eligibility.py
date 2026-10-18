from datetime import datetime, timezone
from types import SimpleNamespace

from app.services.appointment_payment_eligibility import appointment_payment_block_reason


def _appointment(scheduled_for: datetime, status: str = "scheduled"):
    return SimpleNamespace(scheduled_for=scheduled_for, status=status)


def test_payment_eligibility_compares_timezone_aware_instants_not_wall_clock_values():
    now = datetime(2026, 10, 17, 4, 0, tzinfo=timezone.utc)
    # 09:30 in Kolkata is 04:00 UTC, so a 09:15 IST visit is already past.
    past_ist = datetime.fromisoformat("2026-10-17T09:15:00+05:30")
    future_ist = datetime.fromisoformat("2026-10-17T10:00:00+05:30")

    assert appointment_payment_block_reason(_appointment(past_ist), 85000, now=now) == "past"
    assert appointment_payment_block_reason(_appointment(future_ist), 85000, now=now) is None


def test_payment_eligibility_fails_closed_for_naive_database_timestamp():
    now = datetime(2026, 10, 17, 4, 0, tzinfo=timezone.utc)
    naive_utc = datetime(2026, 10, 17, 3, 45)
    assert appointment_payment_block_reason(_appointment(naive_utc), 85000, now=now) == "past"


def test_cancelled_completed_and_zero_fee_appointments_cannot_start_new_payment():
    future = datetime(2026, 10, 20, 4, 30, tzinfo=timezone.utc)
    assert appointment_payment_block_reason(_appointment(future, "cancelled"), 85000) == "cancelled"
    assert appointment_payment_block_reason(_appointment(future, "completed"), 85000) == "not_upcoming"
    assert appointment_payment_block_reason(_appointment(future), 0) == "no_fee"
