from __future__ import annotations

import hashlib
import logging
import math
import re
import time
from typing import Protocol
from urllib.parse import urlsplit, urlunsplit

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmbeddingProviderError(RuntimeError):
    pass


class EmbeddingProvider(Protocol):
    def embed(self, text: str) -> list[float]: ...


def _normalize(vector: list[float]) -> list[float]:
    if not vector or len(vector) > 8192 or any(not math.isfinite(value) for value in vector):
        raise EmbeddingProviderError("Embedding provider returned an invalid vector.")
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        raise EmbeddingProviderError("Embedding provider returned a zero-length vector.")
    return [value / norm for value in vector]


class HashEmbeddingProvider:
    """Deterministic, local lexical baseline; not a semantic embedding model."""

    def embed(self, text: str) -> list[float]:
        tokens = re.findall(r"[^\W_]+", (text or "").casefold(), flags=re.UNICODE)
        if not tokens:
            raise EmbeddingProviderError("Embedding provider requires a non-empty text input.")
        dimensions = max(32, min(settings.embedding_dimensions, 4096))
        vector = [0.0] * dimensions
        for token in tokens:
            bucket = int.from_bytes(hashlib.sha256(token.encode("utf-8")).digest()[:4], "big") % dimensions
            vector[bucket] += 1.0
        return _normalize(vector)


class OpenAICompatibleEmbeddingProvider:
    def embed(self, text: str) -> list[float]:
        headers = {"Authorization": f"Bearer {settings.llm_api_key}"} if settings.llm_api_key else {}
        payload = {"model": settings.embedding_model, "input": text}
        response = _post_with_retries(f"{settings.llm_base_url.rstrip('/')}/embeddings", headers, payload)
        try:
            data = response.json()["data"][0]["embedding"]
        except (KeyError, IndexError, TypeError) as exc:
            raise EmbeddingProviderError("Embedding provider returned a malformed response.") from exc
        if not isinstance(data, list) or not all(isinstance(value, (float, int)) for value in data):
            raise EmbeddingProviderError("Embedding provider returned a malformed vector.")
        return _normalize([float(value) for value in data])


class OllamaEmbeddingProvider:
    def embed(self, text: str) -> list[float]:
        parsed = urlsplit(settings.llm_base_url)
        api_url = urlunsplit((parsed.scheme, parsed.netloc, "/api/embed", "", ""))
        response = _post_with_retries(api_url, {}, {"model": settings.embedding_model, "input": text})
        try:
            data = response.json()["embeddings"][0]
        except (KeyError, IndexError, TypeError) as exc:
            raise EmbeddingProviderError("Ollama returned a malformed embedding response.") from exc
        if not isinstance(data, list) or not all(isinstance(value, (float, int)) for value in data):
            raise EmbeddingProviderError("Ollama returned a malformed embedding vector.")
        return _normalize([float(value) for value in data])


def _post_with_retries(url: str, headers: dict[str, str], payload: dict) -> httpx.Response:
    attempts = 3
    for attempt in range(attempts):
        try:
            with httpx.Client(timeout=max(1.0, settings.embedding_timeout_seconds)) as client:
                response = client.post(url, headers=headers, json=payload)
        except httpx.RequestError as exc:
            if attempt + 1 == attempts:
                logger.warning("Embedding provider request failed after bounded retries.")
                raise EmbeddingProviderError("Could not reach the configured embedding provider.") from exc
            time.sleep(0.1 * (2 ** attempt))
            continue
        if response.status_code not in {408, 429, 500, 502, 503, 504} or attempt + 1 == attempts:
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise EmbeddingProviderError(
                    f"Embedding provider returned HTTP {response.status_code}."
                ) from exc
            return response
        time.sleep(0.1 * (2 ** attempt))
    raise EmbeddingProviderError("Embedding provider retry limit was exceeded.")


def get_embedding_provider() -> EmbeddingProvider:
    provider = settings.embedding_provider.strip().lower()
    providers: dict[str, type[EmbeddingProvider]] = {
        "hash": HashEmbeddingProvider,
        "openai_compatible": OpenAICompatibleEmbeddingProvider,
        "ollama": OllamaEmbeddingProvider,
    }
    implementation = providers.get(provider)
    if implementation is None:
        raise EmbeddingProviderError(f"Unsupported configured embedding provider '{provider}'.")
    return implementation()
