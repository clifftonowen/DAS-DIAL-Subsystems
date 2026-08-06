"""LLMApiClient - singleton facade over TWO independently swappable providers.

Completion and embedding are separate jobs with separate backends, chosen by
`settings.llm_provider` and `settings.embedding_provider`. That split is the point: generation
can run on a hosted model (Gemini) while embeddings stay local (Ollama), because the embedding
model is far more expensive to change — curriculum_chunks is vector(768) and
activity_prompts.MIN_SIMILARITY is tuned to nomic-embed-text's score band, so swapping it means
a migration, a full re-embed, and a re-tuned gate. Swapping the generation model costs nothing.

Every caller does `LLMApiClient()` and gets the same shared instance; no caller knows which
backend is active. Adding one is a class implementing LLMProvider plus a branch in
_build_completion_provider(). Tests override BOTH roles at once via `use_provider(...)`.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Protocol

from app.core.config import settings


class LLMProvider(Protocol):
    """Contract every swappable backend implements.

    One protocol covers both roles even though a provider may only serve one (Gemini does
    generation only): a single fake can then stand in for the whole facade in tests.
    """

    embed_dim: int

    def complete(self, prompt: str, system: str | None = None,
                 temperature: float | None = None, seed: int | None = None) -> str: ...
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
        self.temperature = settings.ollama_temperature
        self.seed = settings.ollama_seed

    def complete(self, prompt: str, system: str | None = None,
                 temperature: float | None = None, seed: int | None = None) -> str:
        import httpx  # lazy: only when a real completion is requested

        # Per-call overrides win; otherwise fall back to the .env/settings defaults.
        # temperature 0 + fixed seed -> deterministic output (reproducible activities).
        payload = {
            "model": self.llm_model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.temperature if temperature is None else temperature,
                "seed": self.seed if seed is None else seed,
            },
        }
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


class GeminiProvider:
    """Google Gemini backend — GENERATION ONLY, over the REST API via httpx.

    Raw httpx rather than an SDK, to match OllamaProvider above: httpx is already a dependency
    and the request shape is a dozen lines. Gemini embeddings are deliberately not wired, so
    embed_many() raises instead of quietly returning vectors the corpus cannot be compared to.
    """

    def __init__(self) -> None:
        self.base_url = settings.gemini_base_url.rstrip("/")
        self.model = settings.gemini_model
        self.api_key = settings.gemini_api_key
        self.temperature = settings.gemini_temperature

    def complete(self, prompt: str, system: str | None = None,
                 temperature: float | None = None, seed: int | None = None) -> str:
        import httpx  # lazy: only when a real completion is requested

        # Raise rather than return placeholder prose (cf. OpenAIProvider below): a generated
        # activity is persisted, so a silent stub would be stored as real curriculum content.
        if not self.api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set — cannot generate. Set it in .env, or switch "
                "generation back to local with LLM_PROVIDER=ollama."
            )

        config: dict = {"temperature": self.temperature if temperature is None else temperature}
        if seed is not None:
            config["seed"] = seed  # best-effort: Gemini does not guarantee Ollama-style repeats
        payload: dict = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": config,
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}

        resp = httpx.post(
            f"{self.base_url}/models/{self.model}:generateContent",
            headers={"x-goog-api-key": self.api_key},
            json=payload,
            timeout=120.0,
        )
        resp.raise_for_status()
        return _gemini_text(resp.json())

    # ── embeddings: not this provider's job ──────────────────────────────
    @property
    def embed_dim(self) -> int:
        raise NotImplementedError(_GEMINI_NO_EMBED)

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError(_GEMINI_NO_EMBED)


_GEMINI_NO_EMBED = (
    "Gemini is wired for generation only — set EMBEDDING_PROVIDER=ollama. The stored corpus is "
    "768-dim nomic-embed-text; embedding with another model would make every vector incomparable."
)


def _gemini_text(body: dict) -> str:
    """First candidate's text. Empty string when the model returned no content (e.g. a safety
    block or a finishReason with no parts) — callers already treat empty output as a refusal."""
    candidates = body.get("candidates") or []
    if not candidates:
        return ""
    parts = (candidates[0].get("content") or {}).get("parts") or []
    return "".join(p.get("text", "") for p in parts)


class OpenAIProvider:
    """OpenAI backend via langchain-openai. Falls back to zero-vectors when no API key
    is configured, so the app stays bootable in dev and dry-run paths never need one."""

    embed_dim = 1536  # text-embedding-3-small; matches vector(1536) in schema.sql
    embedding_model = settings.embedding_model

    def complete(self, prompt: str, system: str | None = None,
                 temperature: float | None = None, seed: int | None = None) -> str:
        # TODO: call langchain-openai ChatOpenAI(model=settings.llm_model, temperature=...) with a system message
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


COMPLETION_PROVIDERS = {"ollama": OllamaProvider, "gemini": GeminiProvider, "openai": OpenAIProvider}
EMBEDDING_PROVIDERS = {"ollama": OllamaProvider, "openai": OpenAIProvider}  # no gemini: see above


@lru_cache(maxsize=1)
def _build_completion_provider() -> LLMProvider:
    """Instantiate the provider named by settings.llm_provider (cached)."""
    name = settings.llm_provider.lower()
    if name not in COMPLETION_PROVIDERS:
        raise ValueError(
            f"Unknown llm_provider: {settings.llm_provider!r} "
            f"(expected one of {sorted(COMPLETION_PROVIDERS)})"
        )
    return COMPLETION_PROVIDERS[name]()


@lru_cache(maxsize=1)
def _build_embedding_provider() -> LLMProvider:
    """Instantiate the provider named by settings.embedding_provider (cached)."""
    name = settings.embedding_provider.lower()
    if name not in EMBEDDING_PROVIDERS:
        raise ValueError(
            f"Unknown embedding_provider: {settings.embedding_provider!r} "
            f"(expected one of {sorted(EMBEDDING_PROVIDERS)})"
        )
    return EMBEDDING_PROVIDERS[name]()


class LLMApiClient:
    """Singleton facade. `LLMApiClient()` always returns the same instance; completion calls go
    to the completion provider and embedding calls to the embedding provider, which may differ."""

    _instance: "LLMApiClient | None" = None
    _override: LLMProvider | None = None

    def __new__(cls) -> "LLMApiClient":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @property
    def completion_provider(self) -> LLMProvider:
        return type(self)._override or _build_completion_provider()

    @property
    def embedding_provider(self) -> LLMProvider:
        return type(self)._override or _build_embedding_provider()

    @property
    def embed_dim(self) -> int:
        return self.embedding_provider.embed_dim

    @property
    def embedding_model(self) -> str:
        """Name of the model that actually produces the vectors — the only honest value for
        curriculum_chunks.embedding_model now that the two backends can differ."""
        return getattr(self.embedding_provider, "embedding_model", "")

    def complete(self, prompt: str, system: str | None = None,
                 temperature: float | None = None, seed: int | None = None) -> str:
        return self.completion_provider.complete(prompt, system, temperature=temperature, seed=seed)

    def embed(self, text: str) -> list[float]:
        return self.embed_many([text])[0]

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return self.embedding_provider.embed_many(list(texts))

    @classmethod
    def use_provider(cls, provider: LLMProvider | None) -> None:
        """Swap the backend at runtime (tests / manual override). One provider stands in for
        BOTH roles, so a single fake covers the whole facade. Pass None to revert to the
        settings-configured providers."""
        cls._override = provider
        _build_completion_provider.cache_clear()
        _build_embedding_provider.cache_clear()
