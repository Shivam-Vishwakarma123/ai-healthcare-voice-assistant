from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.security import get_current_user
from app.core.database import Base, get_db
from app.main import app
from app.models.conversation import AssistantConversation, AssistantMessage
from app.models.knowledge import KnowledgeDocument
from app.models.user import User


def _setup_test_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)

    def override_database():
        with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_database
    return engine, session_factory, TestClient(app)


def test_assistant_health_endpoint():
    """Verify assistant health endpoint distinguishes application health from AI provider health."""
    engine, sessions, client = _setup_test_db()
    try:
        resp = client.get("/api/v1/assistant/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert data["app_healthy"] is True
        assert data["database_connected"] is True
        assert "ai_provider" in data
        assert "embedding_provider" in data
        assert data["ai_provider"]["provider"] in {"ollama", "openai_compatible", "openai"}
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_assessment_endpoints_and_patient_isolation():
    """Verify assessment listing and detail endpoints enforce strict patient isolation."""
    engine, sessions, client = _setup_test_db()
    user_alice = User(id=1, full_name="Alice", email="alice@test.com", password_hash="hash", role="patient")
    user_bob = User(id=2, full_name="Bob", email="bob@test.com", password_hash="hash", role="patient")

    with sessions() as db:
        db.add_all([user_alice, user_bob])
        conv_alice = AssistantConversation(
            id=101,
            user_id=user_alice.id,
            title="Persistent cough with fever",
            urgency_level="routine",
            category="respiratory",
            consent_given=True,
        )
        db.add(conv_alice)
        db.flush()
        msg_alice = AssistantMessage(
            conversation_id=conv_alice.id,
            role="user",
            content="I have had a mild dry cough and slight fever for 3 days",
        )
        msg_asst = AssistantMessage(
            conversation_id=conv_alice.id,
            role="assistant",
            content="This may be a mild viral upper respiratory infection.",
            structured_data={
                "citations": [
                    {
                        "title": "WHO Cough Guidelines",
                        "source_url": "https://www.who.int/cough",
                        "citation": "WHO Cough (v1.0)",
                        "licence": "Open",
                        "allowed_use": "Education",
                        "provenance": "WHO",
                        "retrieval_date": "2026-10-22T10:00:00Z",
                        "version": "1.0",
                    }
                ]
            },
        )
        db.add_all([msg_alice, msg_asst])
        db.commit()
        alice_conv_uuid = conv_alice.conversation_id

    try:
        # Authenticate as Alice: can list and retrieve her assessment
        app.dependency_overrides[get_current_user] = lambda: user_alice

        list_resp = client.get("/api/v1/assistant/assessments")
        assert list_resp.status_code == 200
        assessments = list_resp.json()
        assert len(assessments) == 1
        assert assessments[0]["title"] == "Persistent cough with fever"

        # Alice gets assessment by UUID
        get_uuid = client.get(f"/api/v1/assistant/assessments/{alice_conv_uuid}")
        assert get_uuid.status_code == 200
        detail = get_uuid.json()
        assert detail["assessment_id"] == alice_conv_uuid
        assert detail["symptom_summary"] == "Persistent cough with fever"
        assert len(detail["evidence_sources"]) == 1
        assert detail["evidence_sources"][0]["title"] == "WHO Cough Guidelines"
        assert "disclaimer" in detail

        # Alice gets assessment by integer ID
        get_int = client.get("/api/v1/assistant/assessments/101")
        assert get_int.status_code == 200

        # Switch to Bob: Bob CANNOT access Alice's assessment (strict 404)
        app.dependency_overrides[get_current_user] = lambda: user_bob

        bob_list = client.get("/api/v1/assistant/assessments")
        assert bob_list.status_code == 200
        assert len(bob_list.json()) == 0

        bob_access_uuid = client.get(f"/api/v1/assistant/assessments/{alice_conv_uuid}")
        assert bob_access_uuid.status_code == 404

        bob_access_int = client.get("/api/v1/assistant/assessments/101")
        assert bob_access_int.status_code == 404
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_knowledge_status_role_guard():
    """Verify knowledge status endpoint requires hospital staff or admin privileges."""
    engine, sessions, client = _setup_test_db()
    patient = User(id=1, full_name="Patient", email="pat@test.com", password_hash="h", role="patient")
    admin = User(id=2, full_name="Admin", email="adm@test.com", password_hash="h", role="platform_admin")

    with sessions() as db:
        db.add_all([patient, admin])
        doc = KnowledgeDocument(
            title="Sample Doc",
            source_url="https://www.who.int/test",
            version="1.0",
            licence="Open",
            allowed_use="Testing",
            provenance="WHO",
        )
        db.add(doc)
        db.commit()

    try:
        # Patient is forbidden (403)
        app.dependency_overrides[get_current_user] = lambda: patient
        pat_resp = client.get("/api/v1/assistant/knowledge/status")
        assert pat_resp.status_code == 403

        # Admin is allowed (200)
        app.dependency_overrides[get_current_user] = lambda: admin
        adm_resp = client.get("/api/v1/assistant/knowledge/status")
        assert adm_resp.status_code == 200
        data = adm_resp.json()
        assert data["total_documents"] >= 1
        assert "approved_hosts" in data
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
