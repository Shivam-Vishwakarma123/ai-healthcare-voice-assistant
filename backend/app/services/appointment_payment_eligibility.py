from datetime import datetime, timezone


# Determines whether an appointment is eligible for online payment or returns the blocking reason.
def appointment_payment_block_reason(appointment, fee_minor: int, *, now: datetime | None = None) -> str | None:
    """Return why a new consultation payment cannot be started, using UTC-aware time."""
    if appointment.status == "cancelled":
        return "cancelled"
    if appointment.status not in {"scheduled", "confirmed"}:
        return "not_upcoming"
    scheduled_for = appointment.scheduled_for
    scheduled_for = (
        scheduled_for.replace(tzinfo=timezone.utc)
        if scheduled_for.tzinfo is None
        else scheduled_for.astimezone(timezone.utc)
    )
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None or current_time.utcoffset() is None:
        raise ValueError("Payment eligibility requires a timezone-aware current time.")
    if scheduled_for <= current_time.astimezone(timezone.utc):
        return "past"
    if fee_minor <= 0:
        return "no_fee"
    return None
