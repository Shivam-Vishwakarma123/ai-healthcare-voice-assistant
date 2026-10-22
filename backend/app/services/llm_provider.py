from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel

from app.core.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


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


def format_provider_failure_message(*, provider: str | None = None, model: str | None = None, status_code: int | None = None, detail: str | None = None) -> str:
    provider_label = provider or "configured provider"
    model_label = model or "configured model"
    if status_code:
        return f"AI provider '{provider_label}' ({model_label}) failed with HTTP {status_code}. {detail or 'Check the provider configuration and try again.'}"
    return f"AI provider '{provider_label}' ({model_label}) failed. {detail or 'Check the provider configuration and try again.'}"


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
    def timeout(self) -> httpx.Timeout:
        local_provider = self.name == "ollama"
        total = max(1.0, settings.llm_timeout_seconds)
        return httpx.Timeout(max(total, 180.0) if local_provider else total, connect=min(5.0, total))

    @property
    def retry_limit(self) -> int:
        return max(0, min(settings.llm_max_retries, 3))

    def headers(self) -> dict[str, str]:
        if self.api_key:
            return {"Authorization": f"Bearer {self.api_key}"}
        return {}

    def build_payload(self, messages: list[dict[str, str]], *, response_format: dict[str, Any] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }
        if self.model.startswith("gpt-6-"):
            payload["reasoning_effort"] = "none"
            payload["max_completion_tokens"] = settings.llm_max_tokens
        else:
            payload["temperature"] = settings.llm_temperature
            payload["max_tokens"] = settings.llm_max_tokens
        if response_format is not None:
            payload["response_format"] = response_format
        return payload

    async def complete(self, client: httpx.AsyncClient, messages: list[dict[str, str]], *, response_format: dict[str, Any] | None = None) -> dict[str, Any]:
        for attempt in range(self.retry_limit + 1):
            try:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self.headers(),
                    json=self.build_payload(messages, response_format=response_format),
                )
            except httpx.RequestError:
                if attempt == self.retry_limit:
                    raise
                await asyncio.sleep(0.2 * (2 ** attempt))
                continue
            if response.status_code not in {408, 429, 500, 502, 503, 504} or attempt == self.retry_limit:
                response.raise_for_status()
                return response.json()
            await asyncio.sleep(0.2 * (2 ** attempt))
        raise LLMProviderError("AI provider retry limit was exceeded.", provider=self.name, model=self.model)

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


class OllamaProvider(BaseLLMProvider):
    name = "ollama"
    supports_structured_outputs = True


class OpenAICompatibleProvider(BaseLLMProvider):
    name = "openai_compatible"
    supports_structured_outputs = True


PROVIDER_REGISTRY = {
    "ollama": OllamaProvider,
    "openai": OpenAICompatibleProvider,
    "openai_compatible": OpenAICompatibleProvider,
    "azure_openai": OpenAICompatibleProvider,
}


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
    if len(reply.strip()) > 12000:
        raise LLMProviderError("AI provider returned an excessively long response; refusing to use it.")
    return reply.strip()


def parse_model_json_content(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`\n ")
        if text.lower().startswith("json"):
            text = text[4:].lstrip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMProviderError("AI provider returned malformed JSON. Expected a structured response.") from exc
