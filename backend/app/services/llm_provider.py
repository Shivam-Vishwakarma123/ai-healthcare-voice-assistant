from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel

from app.core.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


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

    # Returns prioritized fallback model chain (primary -> default -> fallback -> alternative).
    def get_fallback_models(self) -> list[str]:
        """Deterministic model fallback chain: primary -> fallback -> alternative."""
        candidates = [
            settings.llm_primary_model,
            self.model,
            settings.llm_fallback_model,
            settings.llm_alternative_model,
        ]
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
        models_to_try = self.get_fallback_models()
        last_exception: Exception | None = None

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
                        if response.status_code >= 500 and model_idx < len(models_to_try) - 1:
                            logger.warning(
                                "Model %s returned HTTP %d. Falling back to %s.",
                                target_model,
                                response.status_code,
                                models_to_try[model_idx + 1],
                            )
                            break
                        response.raise_for_status()
                    return response.json()
                await asyncio.sleep(0.2 * (2 ** attempt))

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
