from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "AI Healthcare Voice Assistant"
    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "postgresql+psycopg://healthcare_user:change_me@localhost:5432/healthcare_db"
    jwt_secret_key: str = "CHANGE_THIS_TO_A_LONG_RANDOM_SECRET_IN_ENV"
    access_token_minutes: int = 20
    password_reset_minutes: int = 30
    auth_rate_limit_attempts: int = 5
    auth_rate_limit_window_seconds: int = 60
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_starttls: bool = True
    sms_api_url: str = ""
    sms_api_token: str = ""
    app_public_url: str = "http://localhost:3000"
    admin_bootstrap_token: str = ""
    backend_cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    llm_provider: str = "ollama"
    llm_api_key: str = ""
    llm_base_url: str = "http://ollama:11434/v1"
    llm_model: str = "llama3.2:1b-instruct-q4_K_M"
    llm_temperature: float = 0.4
    llm_max_tokens: int = 96
    llm_timeout_seconds: float = 45.0
    llm_max_retries: int = 2
    speech_to_text_provider: str = "browser"
    speech_to_text_base_url: str = ""
    speech_to_text_api_key: str = ""
    speech_to_text_model: str = "whisper-1"
    speech_to_text_timeout_seconds: float = 45.0
    speech_to_text_max_audio_bytes: int = 10_485_760
    rag_enabled: bool = False
    embedding_provider: str = "hash"
    embedding_model: str = "text-embedding-3-small"
    embedding_timeout_seconds: float = 15.0
    embedding_dimensions: int = 384
    rag_chunk_size: int = 500
    rag_chunk_overlap: int = 100
    rag_approved_source_hosts: str = "who.int,mohfw.gov.in,mohfw.nic.in,nhs.uk,cdc.gov"
    provider_match_specialty_weight: float = 0.55
    provider_match_city_weight: float = 0.2
    provider_match_language_weight: float = 0.15
    provider_match_consultation_weight: float = 0.1
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""
    razorpay_api_base_url: str = "https://api.razorpay.com/v1"
    razorpay_checkout_config_id: str = ""
    payment_mode: str = "live"
    appointment_refund_policy: str = "manual_review"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    @model_validator(mode="after")
    def validate_production_secrets(self):
        if self.app_env.lower() == "production":
            if self.jwt_secret_key.startswith(("CHANGE_THIS", "replace_")) or len(self.jwt_secret_key) < 32:
                raise ValueError("Set JWT_SECRET_KEY to at least 32 random characters in production.")
            if not self.database_url.startswith(("postgresql://", "postgresql+psycopg://")):
                raise ValueError("Production DATABASE_URL must use PostgreSQL.")
            database_url = urlsplit(self.database_url)
            if not database_url.password or len(database_url.password) < 20:
                raise ValueError("Production DATABASE_URL must contain a strong database password.")
            if self.payment_mode.strip().lower() in {"demo", "test"}:
                raise ValueError("PAYMENT_MODE=demo and PAYMENT_MODE=test are not permitted in production.")
        return self

    @model_validator(mode="after")
    def validate_payment_mode(self):
        self.payment_mode = self.payment_mode.strip().lower()
        self.razorpay_checkout_config_id = self.razorpay_checkout_config_id.strip()
        if self.payment_mode not in {"demo", "live", "test"}:
            raise ValueError("PAYMENT_MODE must be demo, test, or live.")
        if (
            (self.app_env.strip().lower() in {"development", "test"} or self.payment_mode == "test")
            and self.payment_mode in {"live", "test"}
            and self.razorpay_key_id
            and not self.razorpay_key_id.startswith("rzp_test_")
        ):
            raise ValueError("Development and test environments must use Razorpay test keys.")
        self.appointment_refund_policy = self.appointment_refund_policy.strip().lower()
        if self.appointment_refund_policy not in {"manual_review", "no_refunds"}:
            raise ValueError("APPOINTMENT_REFUND_POLICY must be manual_review or no_refunds.")
        return self

    @model_validator(mode="after")
    def validate_ai_limits(self):
        if not 1 <= self.llm_max_tokens <= 8192:
            raise ValueError("LLM_MAX_TOKENS must be between 1 and 8192.")
        if not 1 <= self.llm_timeout_seconds <= 600:
            raise ValueError("LLM_TIMEOUT_SECONDS must be between 1 and 600.")
        if not 0 <= self.llm_max_retries <= 3:
            raise ValueError("LLM_MAX_RETRIES must be between 0 and 3.")
        if not 1 <= self.embedding_timeout_seconds <= 120:
            raise ValueError("EMBEDDING_TIMEOUT_SECONDS must be between 1 and 120.")
        if not 32 <= self.embedding_dimensions <= 4096:
            raise ValueError("EMBEDDING_DIMENSIONS must be between 32 and 4096.")
        if self.rag_chunk_size < 100 or self.rag_chunk_size > 4000:
            raise ValueError("RAG_CHUNK_SIZE must be between 100 and 4000.")
        if not 0 <= self.rag_chunk_overlap < self.rag_chunk_size:
            raise ValueError("RAG_CHUNK_OVERLAP must be smaller than RAG_CHUNK_SIZE.")
        if self.speech_to_text_provider.strip().lower() not in {
            "browser",
            "openai_compatible",
            "indicconformer",
        }:
            raise ValueError("SPEECH_TO_TEXT_PROVIDER must be browser, openai_compatible, or indicconformer.")
        if not 1 <= self.speech_to_text_timeout_seconds <= 180:
            raise ValueError("SPEECH_TO_TEXT_TIMEOUT_SECONDS must be between 1 and 180.")
        if not 1024 <= self.speech_to_text_max_audio_bytes <= 25 * 1024 * 1024:
            raise ValueError("SPEECH_TO_TEXT_MAX_AUDIO_BYTES must be between 1024 and 26214400.")
        return self

    @model_validator(mode="after")
    def validate_auth_configuration(self):
        if not 1 <= self.access_token_minutes <= 1440:
            raise ValueError("ACCESS_TOKEN_MINUTES must be between 1 and 1440.")
        if not 5 <= self.password_reset_minutes <= 120:
            raise ValueError("PASSWORD_RESET_MINUTES must be between 5 and 120.")
        if not 1 <= self.auth_rate_limit_attempts <= 100:
            raise ValueError("AUTH_RATE_LIMIT_ATTEMPTS must be between 1 and 100.")
        if not 1 <= self.auth_rate_limit_window_seconds <= 3600:
            raise ValueError("AUTH_RATE_LIMIT_WINDOW_SECONDS must be between 1 and 3600.")
        smtp_values = (self.smtp_host, self.smtp_from_email)
        if any(smtp_values) and not all(smtp_values):
            raise ValueError("Configure both SMTP_HOST and SMTP_FROM_EMAIL to enable password reset email.")
        if self.smtp_port < 1 or self.smtp_port > 65535:
            raise ValueError("SMTP_PORT must be between 1 and 65535.")
        if bool(self.sms_api_url) != bool(self.sms_api_token):
            raise ValueError("Configure both SMS_API_URL and SMS_API_TOKEN to enable SMS notifications.")
        if self.sms_api_url:
            sms_url = urlsplit(self.sms_api_url)
            if sms_url.scheme != "https" or not sms_url.netloc or sms_url.username or sms_url.password:
                raise ValueError("SMS_API_URL must be an HTTPS URL without embedded credentials.")
        return self

    @model_validator(mode="after")
    def validate_provider_match_weights(self):
        weights = (
            self.provider_match_specialty_weight,
            self.provider_match_city_weight,
            self.provider_match_language_weight,
            self.provider_match_consultation_weight,
        )
        if any(weight < 0 or weight > 1 for weight in weights) or not any(weights):
            raise ValueError("Provider match weights must be between 0 and 1 with a positive total.")
        return self

    @property
    def cors_origins(self) -> list[str]:
        origins = [origin.strip().rstrip("/") for origin in self.backend_cors_origins.split(",") if origin.strip()]
        if "*" in origins:
            raise ValueError("BACKEND_CORS_ORIGINS must not contain '*' when credentials are enabled.")
        for origin in origins:
            parsed = urlsplit(origin)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path or parsed.query or parsed.fragment:
                raise ValueError(f"Invalid CORS origin: {origin}")
        return origins

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
