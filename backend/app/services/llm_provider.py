from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, Field

from app.core.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


# Centralized specification of LLM capabilities, context windows, and pricing.
class ModelCapability(BaseModel):
    model_id: str
    provider: str
    context_window: int = 4096
    max_output_tokens: int = 1024
    supports_structured_outputs: bool = True
    supports_streaming: bool = True
    input_cost_per_million: float = 0.0
    output_cost_per_million: float = 0.0
    is_local: bool = True
    recommended_tasks: list[str] = Field(default_factory=list)


# Centralized capabilities catalog for supported healthcare LLMs.
MODEL_CATALOG: dict[str, ModelCapability] = {
    "llama3.2:1b-instruct-q4_K_M": ModelCapability(
        model_id="llama3.2:1b-instruct-q4_K_M",
        provider="ollama",
        context_window=4096,
        max_output_tokens=1024,
        supports_structured_outputs=True,
        supports_streaming=True,
        input_cost_per_million=0.0,
        output_cost_per_million=0.0,
        is_local=True,
        recommended_tasks=["triage_synthesis", "educational_qa", "patient_summary", "multilingual_basic"],
    ),
    "llama3.2:1b": ModelCapability(
        model_id="llama3.2:1b",
        provider="ollama",
        context_window=4096,
        max_output_tokens=1024,
        supports_structured_outputs=True,
        supports_streaming=True,
        input_cost_per_million=0.0,
        output_cost_per_million=0.0,
        is_local=True,
        recommended_tasks=["triage_synthesis", "educational_qa"],
    ),
    "llama3.2:3b": ModelCapability(
        model_id="llama3.2:3b",
        provider="ollama",
        context_window=8192,
        max_output_tokens=2048,
        supports_structured_outputs=True,
        supports_streaming=True,
        input_cost_per_million=0.0,
        output_cost_per_million=0.0,
        is_local=True,
        recommended_tasks=["soap_notes", "clinical_notes", "medication_reconciliation"],
    ),
    "mistral:7b-instruct-v0.3-q4_K_M": ModelCapability(
        model_id="mistral:7b-instruct-v0.3-q4_K_M",
        provider="ollama",
        context_window=8192,
        max_output_tokens=2048,
        supports_structured_outputs=True,
        supports_streaming=True,
        input_cost_per_million=0.0,
        output_cost_per_million=0.0,
        is_local=True,
        recommended_tasks=["complex_clinical_synthesis", "soap_notes"],
    ),
    "gpt-4o-mini": ModelCapability(
        model_id="gpt-4o-mini",
        provider="openai",
        context_window=128000,
        max_output_tokens=4096,
        supports_structured_outputs=True,
        supports_streaming=True,
        input_cost_per_million=0.15,
        output_cost_per_million=0.60,
        is_local=False,
        recommended_tasks=["triage_synthesis", "soap_notes", "multilingual", "educational_qa"],
    ),
    "gpt-4o": ModelCapability(
        model_id="gpt-4o",
        provider="openai",
        context_window=128000,
        max_output_tokens=4096,
        supports_structured_outputs=True,
        supports_streaming=True,
        input_cost_per_million=2.50,
        output_cost_per_million=10.00,
        is_local=False,
        recommended_tasks=["complex_clinical_synthesis", "soap_notes", "differential_diagnosis"],
    ),
    "gpt-6-astra": ModelCapability(
        model_id="gpt-6-astra",
        provider="openai_compatible",
        context_window=128000,
        max_output_tokens=4096,
        supports_structured_outputs=True,
        supports_streaming=True,
        input_cost_per_million=1.00,
        output_cost_per_million=3.00,
        is_local=False,
        recommended_tasks=["general_triage", "multilingual_qa"],
    ),
}


# Looks up capability metadata for a model name or provides sensible healthcare defaults.
def get_model_capability(model_id: str, provider_hint: str = "ollama") -> ModelCapability:
    if model_id in MODEL_CATALOG:
        return MODEL_CATALOG[model_id]
    return ModelCapability(
        model_id=model_id,
        provider=provider_hint,
        context_window=4096,
        max_output_tokens=1024,
        supports_structured_outputs=True,
        supports_streaming=True,
        is_local=(provider_hint == "ollama"),
        recommended_tasks=["general_healthcare"],
    )


# Represents state transitions for provider circuit breakers.
class CircuitBreakerState:
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


# Circuit breaker protecting against cascade failures when an inference provider is unreachable or failing.
class CircuitBreaker:
    def __init__(self, failure_threshold: int = 3, cooldown_seconds: float = 30.0):
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.consecutive_failures = 0
        self.last_failure_time: float | None = None
        self._state = CircuitBreakerState.CLOSED

    @property
    def state(self) -> str:
        if self._state == CircuitBreakerState.OPEN:
            if self.last_failure_time and (time.time() - self.last_failure_time >= self.cooldown_seconds):
                return CircuitBreakerState.HALF_OPEN
        return self._state

    # Checks whether the circuit breaker permits an execution attempt.
    def can_execute(self) -> tuple[bool, str | None]:
        st = self.state
        if st in {CircuitBreakerState.CLOSED, CircuitBreakerState.HALF_OPEN}:
            return True, None
        remaining = max(0.0, self.cooldown_seconds - (time.time() - (self.last_failure_time or 0)))
        return False, f"Provider circuit breaker is OPEN. Cooldown active for {remaining:.1f}s."

    # Records successful execution, resetting failure counters and closing the circuit.
    def record_success(self) -> None:
        self.consecutive_failures = 0
        self._state = CircuitBreakerState.CLOSED

    # Records an execution failure, tripping the circuit breaker to OPEN if threshold is exceeded.
    def record_failure(self) -> None:
        self.consecutive_failures += 1
        self.last_failure_time = time.time()
        if self.consecutive_failures >= self.failure_threshold:
            self._state = CircuitBreakerState.OPEN
            logger.error("Provider circuit breaker tripped to OPEN after %d consecutive failures.", self.consecutive_failures)

    # Manually resets the circuit breaker to CLOSED state.
    def reset(self) -> None:
        self.consecutive_failures = 0
        self.last_failure_time = None
        self._state = CircuitBreakerState.CLOSED


# Observational telemetry tracker measuring request counts, latencies, tokens, and estimated costs.
class ProviderMetricsTracker:
    def __init__(self):
        self._lock = asyncio.Lock()
        self.total_requests: int = 0
        self.successful_requests: int = 0
        self.failed_requests: int = 0
        self.total_latency_ms: float = 0.0
        self.min_latency_ms: float | None = None
        self.max_latency_ms: float | None = None
        self.prompt_tokens: int = 0
        self.completion_tokens: int = 0
        self.estimated_cost_usd: float = 0.0

    # Thread-safely records completion metrics and token usage.
    async def record_request(
        self,
        *,
        success: bool,
        latency_ms: float,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        async with self._lock:
            self.total_requests += 1
            if success:
                self.successful_requests += 1
            else:
                self.failed_requests += 1
            self.total_latency_ms += latency_ms
            if self.min_latency_ms is None or latency_ms < self.min_latency_ms:
                self.min_latency_ms = latency_ms
            if self.max_latency_ms is None or latency_ms > self.max_latency_ms:
                self.max_latency_ms = latency_ms
            self.prompt_tokens += prompt_tokens
            self.completion_tokens += completion_tokens
            self.estimated_cost_usd += cost_usd

    # Returns an aggregated telemetry snapshot dictionary.
    def get_metrics_snapshot(self) -> dict[str, Any]:
        avg_latency = (self.total_latency_ms / self.total_requests) if self.total_requests > 0 else 0.0
        error_rate = (self.failed_requests / self.total_requests) if self.total_requests > 0 else 0.0
        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "error_rate_pct": round(error_rate * 100, 2),
            "avg_latency_ms": round(avg_latency, 2),
            "min_latency_ms": round(self.min_latency_ms, 2) if self.min_latency_ms is not None else 0.0,
            "max_latency_ms": round(self.max_latency_ms, 2) if self.max_latency_ms is not None else 0.0,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.prompt_tokens + self.completion_tokens,
            "estimated_cost_usd": round(self.estimated_cost_usd, 6),
        }


# Per-provider state registries across request lifecycles.
_shared_circuit_breakers: dict[str, CircuitBreaker] = {}
_shared_metrics: dict[str, ProviderMetricsTracker] = {}
_discovered_models_cache: dict[str, tuple[list[str], float]] = {}


# Custom exception representing failures communicating with LLM inference providers.
class LLMProviderError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        provider: str | None = None,
        model: str | None = None,
        status_code: int | None = None,
        retryable: bool = True,
    ):
        super().__init__(message)
        self.provider = provider
        self.model = model
        self.status_code = status_code
        self.retryable = retryable


# Strips markdown code fences (triple backticks) from LLM output strings.
def strip_markdown_fences(content: str) -> str:
    """Strips markdown code fences (```json ... ``` or ``` ...) from model responses."""
    text = (content or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


# Constructs user-friendly error messages when external AI providers fail.
def format_provider_failure_message(*, provider: str | None = None, model: str | None = None, status_code: int | None = None, detail: str | None = None) -> str:
    provider_label = provider or "configured provider"
    model_label = model or "configured model"
    if status_code:
        return f"AI provider '{provider_label}' ({model_label}) failed with HTTP {status_code}. {detail or 'Check the provider configuration and try again.'}"
    return f"AI provider '{provider_label}' ({model_label}) failed. {detail or 'Check the provider configuration and try again.'}"


# Abstract base class defining common interface and retry mechanisms for LLM providers.
class BaseLLMProvider:
    name = "base"
    supports_structured_outputs = False

    @property
    def base_url(self) -> str:
        return settings.llm_base_url.rstrip("/")

    @property
    def api_key(self) -> str:
        return settings.llm_api_key or ""

    @property
    def model(self) -> str:
        return settings.llm_model

    @property
    def circuit_breaker(self) -> CircuitBreaker:
        if self.name not in _shared_circuit_breakers:
            _shared_circuit_breakers[self.name] = CircuitBreaker()
        return _shared_circuit_breakers[self.name]

    @property
    def metrics(self) -> ProviderMetricsTracker:
        if self.name not in _shared_metrics:
            _shared_metrics[self.name] = ProviderMetricsTracker()
        return _shared_metrics[self.name]

    # Probes the inference provider to discover currently loaded or active models with TTL caching.
    async def discover_available_models(self, client: httpx.AsyncClient, ttl_seconds: float = 60.0) -> list[str]:
        now = time.time()
        cached = _discovered_models_cache.get(self.name)
        if cached:
            models, cache_time = cached
            if now - cache_time < ttl_seconds:
                return models

        models: list[str] = []
        try:
            resp = await client.get(
                f"{self.base_url}/models",
                headers=self.headers(),
                timeout=httpx.Timeout(4.0, connect=2.0),
            )
            if resp.status_code == 200:
                payload = resp.json()
                if isinstance(payload, dict) and "data" in payload and isinstance(payload["data"], list):
                    for item in payload["data"]:
                        if isinstance(item, dict) and "id" in item:
                            models.append(item["id"])
                elif isinstance(payload, list):
                    for item in payload:
                        if isinstance(item, dict) and "id" in item:
                            models.append(item["id"])
                        elif isinstance(item, str):
                            models.append(item)
        except Exception:
            pass

        if not models and self.name == "ollama":
            try:
                resp = await client.get(
                    f"{self.base_url}/api/tags",
                    timeout=httpx.Timeout(4.0, connect=2.0),
                )
                if resp.status_code == 200:
                    payload = resp.json()
                    if isinstance(payload, dict) and "models" in payload and isinstance(payload["models"], list):
                        for item in payload["models"]:
                            if isinstance(item, dict) and "name" in item:
                                models.append(item["name"])
            except Exception:
                pass

        if models:
            _discovered_models_cache[self.name] = (models, now)
        return models

    # Actively checks provider reachability, network latency, and circuit breaker status.
    async def check_connection(self, client: httpx.AsyncClient) -> dict[str, Any]:
        start = time.perf_counter()
        try:
            discovered = await self.discover_available_models(client, ttl_seconds=10.0)
            latency_ms = (time.perf_counter() - start) * 1000
            return {
                "healthy": True,
                "provider": self.name,
                "base_url": self.base_url,
                "latency_ms": round(latency_ms, 2),
                "circuit_breaker_state": self.circuit_breaker.state,
                "available_models": discovered,
                "configured_model": self.model,
            }
        except Exception as exc:
            latency_ms = (time.perf_counter() - start) * 1000
            return {
                "healthy": False,
                "provider": self.name,
                "base_url": self.base_url,
                "latency_ms": round(latency_ms, 2),
                "circuit_breaker_state": self.circuit_breaker.state,
                "configured_model": self.model,
                "error": str(exc),
            }

    # Returns prioritized fallback model chain (primary -> default -> fallback -> alternative).
    def get_fallback_models(self) -> list[str]:
        """Deterministic model fallback chain: self.model -> fallbacks."""
        candidates = [self.model]
        if self.name == "ollama":
            # Filter out hosted/cloud model IDs for local Ollama runtime
            for m in [settings.llm_fallback_model, settings.llm_alternative_model]:
                if m and not m.startswith(("gpt-", "text-", "claude-", "gemini-")):
                    candidates.append(m)
        else:
            for m in [settings.llm_primary_model, settings.llm_fallback_model, settings.llm_alternative_model]:
                if m:
                    candidates.append(m)
        chain: list[str] = []
        for m in candidates:
            if m and m not in chain:
                chain.append(m)
        return chain

    @property
    def timeout(self) -> httpx.Timeout:
        local_provider = self.name == "ollama"
        total = max(1.0, settings.llm_timeout_seconds)
        return httpx.Timeout(max(total, 180.0) if local_provider else total, connect=min(5.0, total))

    @property
    def retry_limit(self) -> int:
        return max(0, min(settings.llm_max_retries, 3))

    # Builds authorization headers containing bearer API keys for provider requests.
    def headers(self) -> dict[str, str]:
        if self.api_key:
            return {"Authorization": f"Bearer {self.api_key}"}
        return {}

    # Constructs OpenAI-compatible chat completion request payloads with token limits.
    def build_payload(
        self,
        messages: list[dict[str, str]],
        *,
        response_format: dict[str, Any] | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        target_model = model or self.model
        payload: dict[str, Any] = {
            "model": target_model,
            "messages": messages,
        }
        if target_model.startswith("gpt-6-"):
            payload["reasoning_effort"] = "none"
            payload["max_completion_tokens"] = settings.llm_max_tokens
        else:
            payload["temperature"] = settings.llm_temperature
            payload["max_tokens"] = settings.llm_max_tokens
        if response_format is not None:
            payload["response_format"] = response_format
        return payload

    # Sends chat completion requests to the provider with exponential-backoff retries and fallback.
    async def complete(
        self,
        client: httpx.AsyncClient,
        messages: list[dict[str, str]],
        *,
        response_format: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        can_exec, reason = self.circuit_breaker.can_execute()
        if not can_exec:
            raise LLMProviderError(
                f"Provider '{self.name}' circuit breaker active: {reason}",
                provider=self.name,
                model=self.model,
                retryable=False,
            )

        models_to_try = self.get_fallback_models()
        last_exception: Exception | None = None
        start_time = time.perf_counter()

        for model_idx, target_model in enumerate(models_to_try):
            for attempt in range(self.retry_limit + 1):
                try:
                    response = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers=self.headers(),
                        json=self.build_payload(messages, response_format=response_format, model=target_model),
                    )
                except httpx.RequestError as exc:
                    last_exception = exc
                    if attempt == self.retry_limit:
                        logger.warning(
                            "Model %s failed on attempt %d: %s. Trying fallback if available.",
                            target_model,
                            attempt,
                            exc,
                        )
                        break
                    await asyncio.sleep(0.2 * (2 ** attempt))
                    continue

                if response.status_code not in {408, 429, 500, 502, 503, 504} or attempt == self.retry_limit:
                    if response.is_error:
                        can_fallback = model_idx < len(models_to_try) - 1
                        if can_fallback and (response.status_code >= 500 or response.status_code == 404):
                            logger.warning(
                                "Model %s returned HTTP %d. Falling back to %s.",
                                target_model,
                                response.status_code,
                                models_to_try[model_idx + 1],
                            )
                            break
                        latency_ms = (time.perf_counter() - start_time) * 1000
                        await self.metrics.record_request(success=False, latency_ms=latency_ms)
                        self.circuit_breaker.record_failure()
                        response.raise_for_status()

                    latency_ms = (time.perf_counter() - start_time) * 1000
                    data = response.json()

                    # Extract or estimate token usage and calculate estimated cost.
                    usage = data.get("usage") if isinstance(data, dict) else None
                    if usage and isinstance(usage, dict):
                        p_tokens = int(usage.get("prompt_tokens") or 0)
                        c_tokens = int(usage.get("completion_tokens") or 0)
                    else:
                        p_words = sum(len(m.get("content", "").split()) for m in messages if isinstance(m, dict))
                        p_tokens = int(p_words * 1.3)
                        reply_text = ""
                        if isinstance(data, dict) and data.get("choices"):
                            reply_text = data["choices"][0].get("message", {}).get("content", "")
                        c_tokens = int(len(reply_text.split()) * 1.3)

                    capability = get_model_capability(target_model, self.name)
                    cost = (p_tokens * capability.input_cost_per_million / 1_000_000.0) + (
                        c_tokens * capability.output_cost_per_million / 1_000_000.0
                    )

                    await self.metrics.record_request(
                        success=True,
                        latency_ms=latency_ms,
                        prompt_tokens=p_tokens,
                        completion_tokens=c_tokens,
                        cost_usd=cost,
                    )
                    self.circuit_breaker.record_success()
                    return data

                await asyncio.sleep(0.2 * (2 ** attempt))

        latency_ms = (time.perf_counter() - start_time) * 1000
        await self.metrics.record_request(success=False, latency_ms=latency_ms)
        self.circuit_breaker.record_failure()

        if last_exception:
            raise last_exception
        raise LLMProviderError(
            f"AI provider retry limit was exceeded for model chain ({', '.join(models_to_try)}).",
            provider=self.name,
            model=self.model,
        )

    # Requests structured JSON outputs from the LLM and validates against a Pydantic schema.
    async def complete_structured(self, client: httpx.AsyncClient, messages: list[dict[str, str]], schema: type[T]) -> T:
        if not self.supports_structured_outputs:
            response = await self.complete(client, messages)
            content = validate_chat_completion_response(response)
            return schema.model_validate_json(content)

        try:
            response = await self.complete(
                client,
                messages,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema.__name__,
                        "strict": True,
                        "schema": schema.model_json_schema(),
                    },
                },
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {400, 422}:
                logger.warning(
                    "Provider %s rejected json_schema with HTTP %d. Retrying with fallback json/standard format.",
                    self.name,
                    exc.response.status_code,
                )
                try:
                    response = await self.complete(
                        client,
                        messages,
                        response_format={"type": "json_object"},
                    )
                except httpx.HTTPStatusError:
                    response = await self.complete(client, messages)
            else:
                raise
        content = validate_chat_completion_response(response)
        try:
            return schema.model_validate_json(content)
        except ValueError:
            try:
                parsed = parse_model_json_content(content)
                return schema.model_validate(parsed)
            except Exception as exc:
                raise LLMProviderError(
                    "AI provider returned content that did not match the required response schema.",
                    provider=self.name,
                    model=self.model,
                    retryable=False,
                ) from exc


# LLM provider implementation for local or hosted Ollama instances.
class OllamaProvider(BaseLLMProvider):
    name = "ollama"
    supports_structured_outputs = True


# Generic LLM provider implementation for OpenAI-compatible HTTP endpoints.
class OpenAICompatibleProvider(BaseLLMProvider):
    name = "openai_compatible"
    supports_structured_outputs = True


PROVIDER_REGISTRY = {
    "ollama": OllamaProvider,
    "openai": OpenAICompatibleProvider,
    "openai_compatible": OpenAICompatibleProvider,
    "azure_openai": OpenAICompatibleProvider,
}


# Factory function returning the configured LLM provider instance.
def get_llm_provider() -> BaseLLMProvider:
    provider_name = (settings.llm_provider or "ollama").strip().lower()
    provider_cls = PROVIDER_REGISTRY.get(provider_name)
    if provider_cls is None:
        raise LLMProviderError(
            f"Unsupported configured AI provider '{provider_name}'.",
            provider=provider_name,
            model=settings.llm_model,
            retryable=False,
        )
    return provider_cls()


# Validates the structure and content of raw chat completion responses.
def validate_chat_completion_response(payload: Any) -> str:
    if not isinstance(payload, dict):
        raise LLMProviderError("AI provider returned an invalid response.")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LLMProviderError("AI provider returned an empty response.")
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise LLMProviderError("AI provider returned an invalid response.")
    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise LLMProviderError("AI provider returned an invalid response.")
    reply = message.get("content")
    if not isinstance(reply, str) or not reply.strip():
        raise LLMProviderError("AI provider returned an empty response.")
    cleaned = strip_markdown_fences(reply.strip())
    if len(cleaned) > 12000:
        raise LLMProviderError("AI provider returned an excessively long response; refusing to use it.")
    return cleaned


# Parses JSON objects from model response strings, handling markdown fences and brackets.
def parse_model_json_content(content: str) -> dict[str, Any]:
    text = strip_markdown_fences(content)
    if text.startswith("```"):
        text = text.strip("`\n ")
        if text.lower().startswith("json"):
            text = text[4:].lstrip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        raise LLMProviderError("AI provider returned malformed JSON. Expected a structured response.") from exc
