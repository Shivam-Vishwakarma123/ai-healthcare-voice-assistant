from fastapi.testclient import TestClient
import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.security import get_current_user
from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.models.user import User
from app.repositories.patient_repository import PatientRepository
from app.routes import assistant_routes
from app.schemas.patient import PatientCreate
from tests.auth_utils import make_session_token


def test_patient_repository_only_returns_rows_for_owner():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        first = User(full_name="First User", email="first@example.com", password_hash="unused")
        second = User(full_name="Second User", email="second@example.com", password_hash="unused")
        db.add_all([first, second])
        db.commit()
        db.refresh(first)
        db.refresh(second)

        repository = PatientRepository()
        patient = repository.create(
            db,
            PatientCreate(full_name="First Profile", email="first-profile@example.com", age=30, gender="other"),
            first.id,
        )

        assert [row.id for row in repository.list(db, first.id)] == [patient.id]
        assert repository.list(db, second.id) == []
        assert repository.get_by_id(db, patient.id, second.id) is None

    engine.dispose()


def test_chat_requires_provider_configuration(monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "")
    monkeypatch.setattr(settings, "llm_base_url", "https://api.openai.com/v1")
    app.dependency_overrides[get_current_user] = lambda: User(
        id=1,
        full_name="Test User",
        email="test@example.com",
        password_hash="unused",
    )
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/assistant/chat",
                json={"messages": [{"role": "user", "content": "Hello"}]},
            )
        assert response.status_code == 503
        assert "LLM_API_KEY" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_local_assistant_works_without_an_api_key(monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "")
    monkeypatch.setattr(settings, "llm_base_url", "http://ollama:11434/v1")
    monkeypatch.setattr(settings, "llm_model", "llama3.2:1b-instruct-q4_K_M")
    request_headers = {}

    def provider_response(request):
        request_headers.update(request.headers)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "{\"reply\":\"I can share general health information.\"}"}}]},
        )

    original_async_client = httpx.AsyncClient
    transport = httpx.MockTransport(provider_response)
    monkeypatch.setattr(
        assistant_routes.httpx,
        "AsyncClient",
        lambda **kwargs: original_async_client(transport=transport, **kwargs),
    )
    app.dependency_overrides[get_current_user] = lambda: User(
        id=1,
        full_name="Test User",
        email="test@example.com",
        password_hash="unused",
    )
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/assistant/chat",
                json={"messages": [{"role": "user", "content": "Hello"}]},
            )
        assert response.status_code == 200
        assert response.json()["reply"].startswith("I can share general health information.")
        assert "Evidence limitation" in response.json()["reply"]
        assert "authorization" not in request_headers
    finally:
        app.dependency_overrides.clear()


def test_unavailable_local_assistant_returns_setup_steps(monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "")
    monkeypatch.setattr(settings, "llm_base_url", "http://ollama:11434/v1")
    monkeypatch.setattr(settings, "llm_model", "llama3.2:1b-instruct-q4_K_M")

    async def raise_connection_error(*args, **kwargs):
        raise httpx.ConnectError("connection refused")

    class UnavailableProvider:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, *args, **kwargs):
            await raise_connection_error()

    monkeypatch.setattr(assistant_routes.httpx, "AsyncClient", lambda **kwargs: UnavailableProvider())
    app.dependency_overrides[get_current_user] = lambda: User(
        id=1,
        full_name="Test User",
        email="test@example.com",
        password_hash="unused",
    )
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/assistant/chat",
                json={"messages": [{"role": "user", "content": "Hello"}]},
            )
        assert response.status_code == 503
        assert "docker compose up -d ollama" in response.json()["detail"]
        assert "docker compose exec ollama ollama pull llama3.2:1b-instruct-q4_K_M" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_patient_routes_require_auth_and_hide_other_accounts():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    test_sessions = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)

    def override_database():
        with test_sessions() as db:
            yield db

    with test_sessions() as db:
        first = User(full_name="First User", email="owner-one@example.com", password_hash="unused")
        second = User(full_name="Second User", email="owner-two@example.com", password_hash="unused")
        db.add_all([first, second])
        db.commit()
        first_token = make_session_token(db, first)
        second_token = make_session_token(db, second)

    app.dependency_overrides[get_db] = override_database
    try:
        with TestClient(app) as client:
            assert client.get("/api/v1/health").json()["status"] == "healthy"
            assert client.get("/api/v1/patients/").status_code == 401
            created = client.post(
                "/api/v1/patients/",
                headers={"Authorization": f"Bearer {first_token}"},
                json={"full_name": "Owner One Profile", "email": "profile-one@example.com", "age": 32, "gender": "other"},
            )
            assert created.status_code == 201
            patient_id = created.json()["id"]

            second_profile = client.get(
                f"/api/v1/patients/{patient_id}",
                headers={"Authorization": f"Bearer {second_token}"},
            )
            assert second_profile.status_code == 404
            second_list = client.get("/api/v1/patients/", headers={"Authorization": f"Bearer {second_token}"})
            assert second_list.json() == []

            first_profile = client.get(
                f"/api/v1/patients/{patient_id}",
                headers={"Authorization": f"Bearer {first_token}"},
            )
            assert first_profile.status_code == 200
            assert first_profile.json()["full_name"] == "Owner One Profile"
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
