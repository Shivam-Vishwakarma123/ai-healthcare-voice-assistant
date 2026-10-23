from fastapi import Request
from sqlalchemy.orm import Session

from app.models.security import AuditLog
from app.models.user import User


# Persists immutable audit log records capturing security actions, actor identity, and network context.
def record_audit(
    db: Session,
    request: Request,
    action: str,
    *,
    actor: User | None = None,
    hospital_id: int | None = None,
    resource_type: str | None = None,
    resource_id: str | int | None = None,
    details: dict | None = None,
) -> None:
    client = request.client
    user_agent = request.headers.get("user-agent", "")
    db.add(
        AuditLog(
            actor_user_id=actor.id if actor else None,
            hospital_id=hospital_id if hospital_id is not None else (actor.hospital_id if actor else None),
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id)[:80] if resource_id is not None else None,
            ip_address=client.host if client else None,
            user_agent=user_agent[:512] or None,
            details=details,
        )
    )
