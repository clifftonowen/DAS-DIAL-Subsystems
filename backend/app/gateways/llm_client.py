"""LLMApiClient - singleton wrapper over a swappable LLM provider.

Completion + embedding both flow through this one object, so the underlying model
(Ollama, OpenAI, ...) can be replaced in a single place. Every caller just does
`LLMApiClient()` and gets the same shared instance; the active backend is chosen by
`settings.llm_provider`. Swap it there, or at runtime via `LLMApiClient.use_provider(...)`.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Protocol

from app.core.config import settings


class LLMProvider(Protocol):
    """Contract every swappable backend implements."""

    embed_dim: int

    def complete(self, prompt: str, system: str | None = None) -> str: ...
    def embed_many(self, texts: list[str]) -> list[list[float]]: ...


class OllamaProvider:
    """Local Ollama backend (default). Talks HTTP to `ollama serve`.

    Completion: llama3.2:latest via /api/generate.
    Embedding:  nomic-embed-text:latest via /api/embeddings (768-dim).
    """

    def __init__(self) -> None:
        self.base_url = settings.ollama_base_url.rstrip("/")
        self.llm_model = settings.ollama_llm_model
        self.embedding_model = settings.ollama_embedding_model
        self.embed_dim = settings.ollama_embedding_dim

    def complete(self, prompt: str, system: str | None = None) -> str:
        import httpx  # lazy: only when a real completion is requested

        payload = {"model": self.llm_model, "prompt": prompt, "stream": False}
        if system:
            payload["system"] = system  # Ollama /api/generate applies this as the system role
        resp = httpx.post(f"{self.base_url}/api/generate", json=payload, timeout=120.0)
        resp.raise_for_status()
        return resp.json().get("response", "")

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        import httpx

        vectors: list[list[float]] = []
        with httpx.Client(timeout=120.0) as client:
            for text in texts:
                resp = client.post(
                    f"{self.base_url}/api/embeddings",
                    json={"model": self.embedding_model, "prompt": text},
                )
                resp.raise_for_status()
                vectors.append(resp.json()["embedding"])
        return vectors


class OpenAIProvider:
    """OpenAI backend via langchain-openai. Falls back to zero-vectors when no API key
    is configured, so the app stays bootable in dev and dry-run paths never need one."""

    embed_dim = 1536  # text-embedding-3-small; matches vector(1536) in schema.sql

    def complete(self, prompt: str, system: str | None = None) -> str:
        # TODO: call langchain-openai ChatOpenAI(model=settings.llm_model) with a system message
        sys_note = f" (system: {len(system)} chars)" if system else ""
        return f"[stub completion for prompt of {len(prompt)} chars{sys_note}]"

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        if not settings.openai_api_key:
            return [[0.0] * self.embed_dim for _ in texts]
        return _openai_embeddings().embed_documents(list(texts))


@lru_cache
def _openai_embeddings():
    from langchain_openai import OpenAIEmbeddings  # lazy: package/key only for real embed

    return OpenAIEmbeddings(model=settings.embedding_model, api_key=settings.openai_api_key)


@lru_cache(maxsize=1)
def _build_provider() -> LLMProvider:
    """Instantiate the provider named by settings.llm_provider (cached)."""
    name = settings.llm_provider.lower()
    if name == "ollama":
        return OllamaProvider()
    if name == "openai":
        return OpenAIProvider()
    raise ValueError(f"Unknown llm_provider: {settings.llm_provider!r} (expected 'ollama' or 'openai')")


class LLMApiClient:
    """Singleton facade. `LLMApiClient()` always returns the same instance, delegating
    to the currently active provider."""

    _instance: "LLMApiClient | None" = None
    _override: LLMProvider | None = None

    def __new__(cls) -> "LLMApiClient":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @property
    def provider(self) -> LLMProvider:
        return type(self)._override or _build_provider()

    @property
    def embed_dim(self) -> int:
        return self.provider.embed_dim

    def complete(self, prompt: str, system: str | None = None) -> str:
        return self.provider.complete(prompt, system)

    def embed(self, text: str) -> list[float]:
        return self.embed_many([text])[0]

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return self.provider.embed_many(list(texts))

    @classmethod
    def use_provider(cls, provider: LLMProvider | None) -> None:
        """Swap the backend at runtime (tests / manual override). Pass None to revert
        to the settings-configured provider."""
        cls._override = provider
        _build_provider.cache_clear()
