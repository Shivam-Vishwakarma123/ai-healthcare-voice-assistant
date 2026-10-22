import argparse
import getpass
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from pathlib import Path

from app.auth.security import hash_password
from app.core.database import SessionLocal
from app.models.providers import Doctor, Hospital
from app.models.security import AuditLog
from app.models.user import User
from app.services.rag_service import RAGDocumentInput, RAGService


def create_account(email: str, role: str, hospital_id: int | None, doctor_id: int | None) -> int:
    normalized_email = email.strip().lower()
    if "@" not in normalized_email:
        print("Enter a valid email address.", file=sys.stderr)
        return 2
    password = getpass.getpass("Staff password (at least 10 characters): ")
    confirmation = getpass.getpass("Confirm password: ")
    if len(password) < 10:
        print("Password must be at least 10 characters.", file=sys.stderr)
        return 2
    if password != confirmation:
        print("Passwords do not match.", file=sys.stderr)
        return 2

    with SessionLocal() as db:
        if role in {"doctor", "hospital_staff", "hospital_admin"}:
            if hospital_id is None or db.get(Hospital, hospital_id) is None:
                print("This role requires a valid --hospital-id.", file=sys.stderr)
                return 2
        elif hospital_id is not None:
            print("Only hospital-scoped roles may specify --hospital-id.", file=sys.stderr)
            return 2
        if role == "doctor":
            doctor = db.get(Doctor, doctor_id) if doctor_id is not None else None
            if doctor is None or doctor.hospital_id != hospital_id or not doctor.is_active:
                print("Doctor accounts require an active --doctor-id at the selected hospital.", file=sys.stderr)
                return 2
        elif doctor_id is not None:
            print("--doctor-id may only be used with the doctor role.", file=sys.stderr)
            return 2
        existing = db.scalar(select(User).where(User.email == normalized_email))
        if existing is not None:
            if (
                existing.role != role
                or existing.hospital_id is not None
                or existing.doctor_id is not None
                or role not in {"doctor", "hospital_staff", "hospital_admin"}
            ):
                print("An account with that email already exists and cannot be safely reprovisioned.", file=sys.stderr)
                return 2
            existing.hospital_id = hospital_id
            existing.doctor_id = doctor_id
            existing.password_hash = hash_password(password)
            _record_account_provisioning(db, existing)
            db.commit()
            print(f"Unassigned {role.replace('_', ' ')} account provisioned for {normalized_email}.")
            return 0
        user = User(
            full_name=" ".join(part.capitalize() for part in role.split("_")),
            email=normalized_email,
            password_hash=hash_password(password),
            role=role,
            hospital_id=hospital_id,
            doctor_id=doctor_id,
        )
        db.add(user)
        db.flush()
        _record_account_provisioning(db, user)
        db.commit()
    print(f"{role.replace('_', ' ').capitalize()} account created for {normalized_email}.")
    return 0


def _record_account_provisioning(db: Session, user: User) -> None:
    db.add(
        AuditLog(
            hospital_id=user.hospital_id,
            action="account.provisioned",
            resource_type="user",
            resource_id=str(user.id),
            details={"role": user.role},
        )
    )


def ingest_knowledge_manifest(manifest_path: Path | None = None) -> int:
    import json
    from datetime import datetime

    path = manifest_path or (Path(__file__).resolve().parents[1] / "data" / "knowledge" / "manifest.jsonl")
    if not path.is_file():
        print(f"Manifest file not found: {path}", file=sys.stderr)
        return 2

    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))

    service = RAGService()
    with SessionLocal() as db:
        for record in records:
            content_path = (path.parent / record.pop("content_file")).resolve()
            content = content_path.read_text(encoding="utf-8")
            pub_date = datetime.fromisoformat(record["publication_date"]) if record.get("publication_date") else None
            upd_date = datetime.fromisoformat(record["updated_at"]) if record.get("updated_at") else None
            service.ingest_document(
                db,
                RAGDocumentInput(
                    title=record["title"],
                    source_url=record["source_url"],
                    content=content,
                    publication_date=pub_date,
                    updated_at=upd_date,
                    version=record["version"],
                    licence=record["licence"],
                    allowed_use=record["allowed_use"],
                    provenance=record["provenance"],
                    category="public_health",
                    language=record.get("language", "en"),
                    summary=record.get("summary"),
                    metadata=record.get("metadata"),
                ),
            )
        db.commit()
    print(f"Successfully ingested/refreshed {len(records)} knowledge documents into RAG database.")
    return 0


def run_seed_demo() -> int:
    from app.seed_demo import seed_demo_data

    with SessionLocal.begin() as db:
        counts = seed_demo_data(db)
    print(f"CareVoice demo data successfully seeded: {counts}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="CareVoice account administration")
    subparsers = parser.add_subparsers(dest="command", required=True)
    account_parser = subparsers.add_parser("create-account", help="Provision a trusted application account")
    account_parser.add_argument("email")
    account_parser.add_argument(
        "--role",
        required=True,
        choices=("doctor", "hospital_staff", "hospital_admin", "platform_admin"),
    )
    account_parser.add_argument("--hospital-id", type=int)
    account_parser.add_argument("--doctor-id", type=int)

    knowledge_parser = subparsers.add_parser("ingest-knowledge", help="Ingest reviewed medical knowledge corpus into RAG database")
    knowledge_parser.add_argument("--manifest", type=Path, default=None, help="Optional path to manifest.jsonl")

    subparsers.add_parser("seed-demo", help="Seed realistic synthetic demo data for patient and clinician demonstration")

    args = parser.parse_args()
    if args.command == "create-account":
        return create_account(args.email, args.role, args.hospital_id, args.doctor_id)
    if args.command == "ingest-knowledge":
        return ingest_knowledge_manifest(args.manifest)
    if args.command == "seed-demo":
        return run_seed_demo()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
