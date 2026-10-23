import logging
import smtplib
from email.message import EmailMessage

import httpx
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.security import NotificationDelivery
from app.models.user import User

logger = logging.getLogger(__name__)


# Dispatches multi-channel email and SMS alerts to a user and logs delivery audit records.
def notify_user(
    db: Session,
    user: User,
    event_type: str,
    *,
    hospital_id: int | None = None,
) -> dict[str, str]:
    outcomes: dict[str, str] = {}
    email_status = _send_email(user.email) if settings.smtp_host and settings.smtp_from_email else "unconfigured"
    _record_delivery(db, user, hospital_id, "email", event_type, email_status)
    outcomes["email"] = email_status

    if not user.phone_number:
        sms_status = "no_recipient"
    elif not settings.sms_api_url or not settings.sms_api_token:
        sms_status = "unconfigured"
    else:
        sms_status = _send_sms(user.phone_number)
    _record_delivery(db, user, hospital_id, "sms", event_type, sms_status)
    outcomes["sms"] = sms_status
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error("Notification delivery outcomes could not be recorded (%s)", type(exc).__name__)
        return {channel: "tracking_failed" for channel in outcomes}
    return outcomes


# Sends transactional notification emails via SMTP with optional TLS encryption.
def _send_email(recipient: str) -> str:
    try:
        message = EmailMessage()
        message["Subject"] = "CareVoice notification"
        message["From"] = settings.smtp_from_email
        message["To"] = recipient
        message.set_content("You have a new CareVoice notification. Sign in to your account for details.")
        if settings.smtp_port == 465:
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=10) as server:
                if settings.smtp_username:
                    server.login(settings.smtp_username, settings.smtp_password)
                server.send_message(message)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
                server.ehlo()
                if settings.smtp_starttls:
                    server.starttls()
                    server.ehlo()
                if settings.smtp_username:
                    server.login(settings.smtp_username, settings.smtp_password)
                server.send_message(message)
        return "sent"
    except (OSError, smtplib.SMTPException) as exc:
        logger.warning("Notification email delivery failed (%s)", type(exc).__name__)
        return "failed"


# Sends transactional notification SMS messages via external HTTP gateway.
def _send_sms(recipient: str) -> str:
    try:
        response = httpx.post(
            settings.sms_api_url,
            json={
                "to": recipient,
                "message": "You have a new CareVoice notification. Sign in to your account for details.",
            },
            headers={"Authorization": f"Bearer {settings.sms_api_token}"},
            timeout=httpx.Timeout(10.0, connect=3.0),
        )
        response.raise_for_status()
        return "sent"
    except httpx.HTTPStatusError as exc:
        logger.warning("Notification SMS provider returned HTTP %s", exc.response.status_code)
        return "failed"
    except httpx.RequestError as exc:
        logger.warning("Notification SMS delivery failed (%s)", type(exc).__name__)
        return "failed"


# Inserts a delivery attempt tracking record into the database.
def _record_delivery(
    db: Session,
    user: User,
    hospital_id: int | None,
    channel: str,
    event_type: str,
    result: str,
) -> None:
    db.add(
        NotificationDelivery(
            user_id=user.id,
            hospital_id=hospital_id if hospital_id is not None else user.hospital_id,
            channel=channel,
            event_type=event_type[:80],
            status=result,
            failure_code=result if result in {"failed", "unconfigured", "no_recipient"} else None,
        )
    )
