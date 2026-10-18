import pytest

from app.core.config import Settings
from app.models import Appointment, Doctor, Hospital, KnowledgeChunk, KnowledgeDocument, Refund


def test_model_registry_contains_provider_and_knowledge_models():
    assert {
        "appointments",
        "doctors",
        "hospitals",
        "knowledge_chunks",
        "knowledge_documents",
        "payment_refunds",
    }.issubset(Appointment.metadata.tables)
    assert Appointment.metadata is Doctor.metadata is Hospital.metadata
    assert KnowledgeChunk.metadata is KnowledgeDocument.metadata
    assert Refund.metadata is Appointment.metadata


def test_cors_origins_are_normalized_and_wildcards_rejected():
    settings = Settings(
        _env_file=None,
        backend_cors_origins=" https://portal.example/,http://localhost:3000 ",
    )
    assert settings.cors_origins == ["https://portal.example", "http://localhost:3000"]

    wildcard = Settings(_env_file=None, backend_cors_origins="*")
    with pytest.raises(ValueError, match="must not contain"):
        _ = wildcard.cors_origins


def test_production_configuration_rejects_weak_database_password():
    with pytest.raises(ValueError, match="strong database password"):
        Settings(
            _env_file=None,
            app_env="production",
            jwt_secret_key="x" * 64,
            database_url="postgresql+psycopg://service:weak@db/healthcare",
        )


def test_development_live_mode_rejects_razorpay_live_key():
    with pytest.raises(ValueError, match="must use Razorpay test keys"):
        Settings(
            _env_file=None,
            app_env="development",
            payment_mode="live",
            razorpay_key_id="rzp_live_example",
        )


def test_refund_policy_only_accepts_explicit_supported_modes():
    assert Settings(_env_file=None).appointment_refund_policy == "manual_review"
    with pytest.raises(ValueError, match="APPOINTMENT_REFUND_POLICY"):
        Settings(_env_file=None, appointment_refund_policy="automatic_full_refund")
