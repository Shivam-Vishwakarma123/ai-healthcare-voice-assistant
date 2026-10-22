from __future__ import annotations

from datetime import datetime, timezone
import httpx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, settings
from app.core.database import Base, get_db
from app.main import app
from app.models.conversation import AssistantConversation, AssistantMessage
from app.models.patient import Patient
from app.models.providers import Doctor, DoctorSchedule, Hospital
from app.models.user import User
from app.routes import assistant_routes
from app.services.doctor_recommendation_service import get_verified_doctor_recommendations
from app.services.rag_service import RAGDocumentInput, RAGService
from app.services.triage_service import evaluate_triage


def _setup_test_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)

    def override_database():
        with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_database
    return engine, session_factory, TestClient(app)


def test_ai_settings_bidirectional_sync():
    """Verify AI_* and LLM_*/EMBEDDING_* environment variables synchronize accurately."""
    s1 = Settings(ai_provider="ollama", ai_model="llama3.2:1b-instruct-q4_K_M")
    assert s1.llm_provider == "ollama"
    assert s1.llm_model == "llama3.2:1b-instruct-q4_K_M"

    s2 = Settings(llm_provider="openai_compatible", llm_model="gpt-6-astra")
    assert s2.ai_provider == "openai_compatible"
    assert s2.ai_model == "gpt-6-astra"


def test_triage_extended_fields_and_urgency_levels():
    """Verify clinical triage produces rich structured fields with deterministic emergency prioritization."""
    # Emergency case
    res_em = evaluate_triage("Severe crushing chest pain radiating to left arm with breathlessness")
    assert res_em.urgency == "emergency"
    assert res_em.urgency_level == "emergency"
    assert "112" in res_em.emergency_numbers
    assert "108" in res_em.emergency_numbers
    assert "chest_pain" in res_em.flags
    assert res_em.emergency_warning is not None

    # Ambiguous/routine case
    res_rt = evaluate_triage("I had a mild sore throat yesterday and sneezed once")
    assert res_rt.urgency in {"routine", "urgent"}
    assert res_rt.emergency_warning is None
    assert len(res_rt.follow_up_questions) > 0
    assert len(res_rt.possible_explanations) > 0
    assert len(res_rt.recommended_next_steps) > 0
    assert "health education and navigation assistance only" in res_rt.disclaimer


def test_multilingual_emergency_red_flags():
    """Verify emergency red flags trigger across English, Hindi, Hinglish, and Tele-MANAS crisis."""
    # Hinglish cardiac emergency
    res1 = evaluate_triage("Mujhe seene me bahut tez dard ho raha hai aur chakkar aa rahe hain")
    assert res1.urgency == "emergency"
    assert "112" in res1.emergency_numbers

    # Devanagari Hindi respiratory emergency
    res2 = evaluate_triage("सांस लेने में बहुत तकलीफ हो रही है और होंठ नीले पड़ रहे हैं")
    assert res2.urgency == "emergency"
    assert "112" in res2.emergency_numbers
    assert "108" in res2.emergency_numbers

    # Tele-MANAS mental health crisis in Hindi
    res3 = evaluate_triage("Mujhe jeene ka koi matlab nahi lagta, suicide ka mann kar raha hai")
    assert res3.urgency == "emergency"
    assert res3.category == "mental_health"
    assert "Tele-MANAS 14416" in res3.emergency_numbers


def test_conversation_persistence_and_lifecycle():
    """Test full CRUD lifecycle of patient consultations with explicit consent."""
    engine, sessions, client = _setup_test_db()
    user = User(id=10, full_name="Patient User", email="patient10@example.com", password_hash="hash", role="patient")
    with sessions() as db:
        db.add(user)
        db.commit()

    app.dependency_overrides[assistant_routes.get_current_user] = lambda: user

    try:
        # Create conversation
        create_resp = client.post(
            "/api/v1/assistant/conversations",
            json={"title": "Follow up consultation", "consent_given": True},
        )
        assert create_resp.status_code == 201
        conv_id = create_resp.json()["id"]

        # List conversations
        list_resp = client.get("/api/v1/assistant/conversations")
        assert list_resp.status_code == 200
        assert len(list_resp.json()) == 1
        assert list_resp.json()[0]["id"] == conv_id

        # Get specific conversation
        get_resp = client.get(f"/api/v1/assistant/conversations/{conv_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["title"] == "Follow up consultation"

        # Delete conversation
        del_resp = client.delete(f"/api/v1/assistant/conversations/{conv_id}")
        assert del_resp.status_code == 200
        assert del_resp.json()["deleted"] is True

        # Confirm deleted
        get_after = client.get(f"/api/v1/assistant/conversations/{conv_id}")
        assert get_after.status_code == 404
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_cross_patient_data_isolation():
    """Verify strict tenant isolation prevents Patient B from viewing or modifying Patient A's conversations."""
    engine, sessions, client = _setup_test_db()
    user_a = User(id=1, full_name="Patient A", email="a@example.com", password_hash="hash", role="patient")
    user_b = User(id=2, full_name="Patient B", email="b@example.com", password_hash="hash", role="patient")

    with sessions() as db:
        db.add_all([user_a, user_b])
        conv_a = AssistantConversation(user_id=user_a.id, title="Patient A Secret History", consent_given=True)
        db.add(conv_a)
        db.commit()
        conv_a_id = conv_a.id

    try:
        # Authenticate as Patient B
        app.dependency_overrides[assistant_routes.get_current_user] = lambda: user_b

        # Patient B tries to get Patient A's conversation
        resp = client.get(f"/api/v1/assistant/conversations/{conv_a_id}")
        assert resp.status_code == 404

        # Patient B tries to delete Patient A's conversation
        del_resp = client.delete(f"/api/v1/assistant/conversations/{conv_a_id}")
        assert del_resp.status_code == 404

        # Patient B listing only shows their own (empty)
        list_resp = client.get("/api/v1/assistant/conversations")
        assert list_resp.status_code == 200
        assert len(list_resp.json()) == 0
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_chat_respects_privacy_consent():
    """Verify chat without consent stores no database records, but persists when consent is given."""
    engine, sessions, client = _setup_test_db()
    user = User(id=5, full_name="Consent Tester", email="consent@example.com", password_hash="hash", role="patient")
    with sessions() as db:
        db.add(user)
        db.commit()

    app.dependency_overrides[assistant_routes.get_current_user] = lambda: user

    try:
        # Chat without consent (emergency triage bypasses LLM cleanly)
        resp_no_consent = client.post(
            "/api/v1/assistant/chat",
            json={
                "messages": [{"role": "user", "content": "I have sudden severe chest pain"}],
                "consent_to_store": False,
            },
        )
        assert resp_no_consent.status_code == 200
        assert resp_no_consent.json()["conversation_id"] is None

        with sessions() as db:
            count = db.scalar(select(AssistantConversation).where(AssistantConversation.user_id == user.id))
            assert count is None

        # Chat with explicit consent
        resp_with_consent = client.post(
            "/api/v1/assistant/chat",
            json={
                "messages": [{"role": "user", "content": "I have sudden severe chest pain"}],
                "consent_to_store": True,
            },
        )
        assert resp_with_consent.status_code == 200
        conv_id = resp_with_consent.json()["conversation_id"]
        assert conv_id is not None

        with sessions() as db:
            conv = db.scalar(select(AssistantConversation).where(AssistantConversation.id == conv_id))
            assert conv is not None
            assert conv.consent_given is True
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_verified_doctor_recommendations_filtering():
    """Verify doctor recommendations include only active, verified clinicians with explainable criteria."""
    engine, sessions, _ = _setup_test_db()

    with sessions() as db:
        hospital = Hospital(
            id=1,
            name="Apollo General",
            city="Bengaluru",
            verified=True,
            verification_status="verified",
            state="Karnataka",
            address="Bannerghatta Rd",
        )
        # Doctor 1: Cardiology, active, verified
        doc_cardio = Doctor(
            id=1,
            hospital_id=1,
            full_name="Rajesh Sharma",
            specialty="Cardiology",
            experience_years=15,
            verification_status="verified",
            is_active=True,
            fee_minor=80000,
        )
        # Doctor 2: Inactive doctor
        doc_inactive = Doctor(
            id=2,
            hospital_id=1,
            full_name="Inactive Clinician",
            specialty="Cardiology",
            experience_years=5,
            verification_status="verified",
            is_active=False,
            fee_minor=50000,
        )
        # Doctor 3: Unverified doctor
        doc_unverified = Doctor(
            id=3,
            hospital_id=1,
            full_name="Unverified Clinician",
            specialty="Cardiology",
            experience_years=8,
            verification_status="pending",
            is_active=True,
            fee_minor=60000,
        )
        # Doctor 4: General Medicine
        doc_gen = Doctor(
            id=4,
            hospital_id=1,
            full_name="Ananya Patel",
            specialty="General Medicine",
            experience_years=10,
            verification_status="verified",
            is_active=True,
            fee_minor=50000,
        )
        db.add_all([hospital, doc_cardio, doc_inactive, doc_unverified, doc_gen])
        db.commit()

        # Query for chest pain / cardiology
        recs = get_verified_doctor_recommendations(db, symptoms="chest discomfort", specialty="Cardiology")
        doc_ids = [r.doctor_id for r in recs]
        assert doc_cardio.id in doc_ids
        assert doc_inactive.id not in doc_ids
        assert doc_unverified.id not in doc_ids

        # Verify explainable criteria
        top_rec = recs[0]
        assert any("Cardiology" in reason for reason in top_rec.match_reasons)
        assert top_rec.fee_minor == 80000

    engine.dispose()
