"""LLMApiClient - singleton facade over TWO independently swappable providers.

Completion and embedding are separate jobs with separate backends, chosen by
`settings.llm_provider` and `settings.embedding_provider`. That split is the point: swapping the
generation model costs nothing, while swapping the embedding model costs a full re-embed and a
re-tuned retrieval gate — `activity_prompts.MIN_SIMILARITY` is calibrated to one model's score
band, and every model has a different one. The DIMENSION is no longer the obstacle it once was
(Gemini's Matryoshka output truncates to 768, matching curriculum_chunks), but the score band
still is, which is why the gate now lives in settings rather than in a constant.

ASYMMETRIC EMBEDDING. `embed_many(..., is_query=True)` marks text as a search QUERY rather than a
stored DOCUMENT. Retrieval-trained embedders encode the two differently — the same sentence gets
two different vectors — and using the right one is worth more than any other single knob here.
Providers that cannot do it ignore the flag, so it is always safe to pass.

Every caller does `LLMApiClient()` and gets the same shared instance; no caller knows which
backend is active. Adding one is a class implementing LLMProvider plus an entry in the
COMPLETION_PROVIDERS / EMBEDDING_PROVIDERS maps. Tests override BOTH roles at once via
`use_provider(...)`.
"""
from __future__ import annotations

import math
from functools import lru_cache
from typing import Protocol

from app.core.config import settings


class LLMProvider(Protocol):
    """Contract every swappable backend implements.

    One protocol covers both roles even though a provider may only serve one (Claude does
    generation only): a single fake can then stand in for the whole facade in tests.
    """

    embed_dim: int

    def complete(self, prompt: str, system: str | None = None,
                 temperature: float | None = None, seed: int | None = None) -> str: ...
    def embed_many(self, texts: list[str], *, is_query: bool = False) -> list[list[float]]: ...


def _unit(vector: list[float]) -> list[float]:
    """L2-normalise so cosine similarity is a plain dot product.

    Needed because Matryoshka models return UNNORMALISED vectors when you truncate below their
    native width (gemini-embedding-001 at 768 arrives with ‖v‖ ≈ 0.59). pgvector's `<=>` normalises
    internally so ranking would survive either way, but anything that reads the raw vector — an
    offline eval, a dot-product index, a future switch to `<#>` — silently would not.
    """
    norm = math.sqrt(sum(x * x for x in vector))
    return [x / norm for x in vector] if norm else vector


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

    def embed_many(self, texts: list[str], *, is_query: bool = False) -> list[list[float]]:
        import httpx

        prefix = self._task_prefix(is_query)
        vectors: list[list[float]] = []
        with httpx.Client(timeout=120.0) as client:
            for text in texts:
                resp = client.post(
                    f"{self.base_url}/api/embeddings",
                    json={"model": self.embedding_model, "prompt": prefix + text},
                )
                resp.raise_for_status()
                vectors.append(resp.json()["embedding"])
        return vectors

    def _task_prefix(self, is_query: bool) -> str:
        """nomic-embed-text's `search_query:` / `search_document:` prefixes — OFF by default.

        The model is trained to expect them and omitting them measurably degrades retrieval, so
        the tempting move is to just switch them on. Do not, on its own: the stored corpus was
        embedded WITHOUT them, and prefixing only the query side pairs a prefixed query against
        unprefixed documents, which is worse than the consistent-but-suboptimal state we are in.

        Flip OLLAMA_USE_TASK_PREFIXES to true and re-embed the corpus in the same change, or not
        at all. Ignored by models that do not use prefixes.
        """
        if not settings.ollama_use_task_prefixes:
            return ""
        return "search_query: " if is_query else "search_document: "


class GeminiProvider:
    """Google Gemini backend for GENERATION, over the REST API via httpx.

    Raw httpx rather than an SDK, to match OllamaProvider above: httpx is already a dependency
    and the request shape is a dozen lines. Embeddings live in GeminiEmbeddingProvider below —
    a separate class because the two roles share a vendor and a key but nothing else, and
    because `embedding_provider = "gemini"` should not drag a completion model along with it.
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

    # ── embeddings: a different class's job ──────────────────────────────
    @property
    def embed_dim(self) -> int:
        raise NotImplementedError(_GEMINI_GEN_ONLY)

    def embed_many(self, texts: list[str], *, is_query: bool = False) -> list[list[float]]:
        raise NotImplementedError(_GEMINI_GEN_ONLY)


_GEMINI_GEN_ONLY = (
    "GeminiProvider does generation only. For Gemini embeddings set EMBEDDING_PROVIDER=gemini, "
    "which selects GeminiEmbeddingProvider — a separate class with its own model setting."
)


class GeminiEmbeddingProvider:
    """Google Gemini embeddings — EMBEDDING ONLY, over the REST API via httpx.

    Two properties make this usable as a drop-in for the existing corpus:

    MATRYOSHKA TRUNCATION. `outputDimensionality` cuts the native 3072-dim output down to 768
    without retraining, so curriculum_chunks stays vector(768) and neither RPC signature moves.
    The vectors are still incomparable to the previous model's — every model has its own space —
    but that costs a re-embed, not a migration.

    TASK TYPES. RETRIEVAL_QUERY vs RETRIEVAL_DOCUMENT produce different vectors for the same text,
    which is the whole point of `is_query`. Verify this against any model you point it at rather
    than assuming: `gemini-embedding-2` ACCEPTS taskType (a bogus value 400s) and then ignores it —
    query and document embeddings come back bit-identical — while `gemini-embedding-001` honours
    it. Measured on this corpus, that difference is worth ~0.08 MRR and nearly double the gap
    between real and junk queries, which is what MIN_SIMILARITY has to discriminate.
    """

    BATCH = 64          # requests per :batchEmbedContents call
    MAX_RETRIES = 4     # 429/5xx only — these are rate limits, not bad requests

    def __init__(self) -> None:
        self.base_url = settings.gemini_base_url.rstrip("/")
        self.embedding_model = settings.gemini_embedding_model
        self.api_key = settings.gemini_api_key
        self.embed_dim = settings.gemini_embedding_dim

    def complete(self, prompt: str, system: str | None = None,
                 temperature: float | None = None, seed: int | None = None) -> str:
        raise NotImplementedError(
            "GeminiEmbeddingProvider does embeddings only — set LLM_PROVIDER=gemini for generation."
        )

    def embed_many(self, texts: list[str], *, is_query: bool = False) -> list[list[float]]:
        import time

        import httpx  # lazy: only when a real embedding is requested

        # Raise rather than return zero-vectors (cf. OpenAIProvider below): zero vectors have
        # undefined cosine distance, so they do not fail — they rank arbitrarily, and the corpus
        # ends up holding vectors nobody can tell apart from real ones.
        if not self.api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set — cannot embed. Set it in .env, or switch embeddings "
                "back to local with EMBEDDING_PROVIDER=ollama."
            )

        task = "RETRIEVAL_QUERY" if is_query else "RETRIEVAL_DOCUMENT"
        vectors: list[list[float]] = []
        with httpx.Client(timeout=180.0) as client:
            for start in range(0, len(texts), self.BATCH):
                batch = texts[start:start + self.BATCH]
                payload = {"requests": [
                    {
                        "model": f"models/{self.embedding_model}",
                        "content": {"parts": [{"text": text}]},
                        "outputDimensionality": self.embed_dim,
                        "taskType": task,
                    }
                    for text in batch
                ]}
                resp = self._post_with_retry(client, payload, time.sleep)
                vectors.extend(_unit(e["values"]) for e in resp.json()["embeddings"])
        return vectors

    def _post_with_retry(self, client, payload: dict, sleep):
        """POST a batch, backing off on rate limits. A 400 is our bug and must surface at once."""
        import httpx

        last: httpx.Response | None = None
        for attempt in range(self.MAX_RETRIES):
            last = client.post(
                f"{self.base_url}/models/{self.embedding_model}:batchEmbedContents",
                headers={"x-goog-api-key": self.api_key},
                json=payload,
            )
            if last.status_code != 429 and last.status_code < 500:
                break
            sleep(2 ** attempt)
        assert last is not None
        last.raise_for_status()
        return last


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

    def embed_many(self, texts: list[str], *, is_query: bool = False) -> list[list[float]]:
        if not settings.openai_api_key:
            return [[0.0] * self.embed_dim for _ in texts]
        # OpenAI embeddings are symmetric — one encoder, no query/document distinction.
        return _openai_embeddings().embed_documents(list(texts))


@lru_cache
def _openai_embeddings():
    from langchain_openai import OpenAIEmbeddings  # lazy: package/key only for real embed

    return OpenAIEmbeddings(model=settings.embedding_model, api_key=settings.openai_api_key)


class ClaudeProvider:
    """Anthropic Claude backend — GENERATION ONLY, over the Messages API via httpx.

    Exists so the generator can be A/B'd across vendors on one golden set. Embeddings are not
    wired because Anthropic does not serve an embedding model.

    Two ways it differs from the other completion providers, both load-bearing:

    `max_tokens` is REQUIRED by the Messages API — there is no "unlimited" — so this is the only
    provider here that caps output. Set it high enough for a full activity (title, objective,
    materials, numbered steps); too low truncates mid-step and the truncation looks like a
    perfectly ordinary short activity to everything downstream.

    There is NO seed parameter, and on the Claude 5 family no temperature either — those models
    reject `temperature` with a 400 rather than ignoring it, so it is omitted unless explicitly
    configured. `seed` is likewise accepted and ignored rather than rejected, so callers
    (scripts.generate_activity passes one) need not branch on the provider. The upshot: this
    provider cannot offer reproducibility at all, not even Gemini's best-effort kind. Nothing
    automated depends on that today, but do not write a test that assumes it.
    """

    def __init__(self) -> None:
        self.base_url = settings.anthropic_base_url.rstrip("/")
        self.model = settings.claude_model
        self.api_key = settings.anthropic_api_key
        self.temperature = settings.claude_temperature
        self.max_tokens = settings.claude_max_tokens

    def complete(self, prompt: str, system: str | None = None,
                 temperature: float | None = None, seed: int | None = None) -> str:
        import httpx  # lazy: only when a real completion is requested

        # Raise rather than return placeholder prose (cf. OpenAIProvider above): a generated
        # activity is persisted, so a silent stub would be stored as real curriculum content.
        if not self.api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set — cannot generate. Set it in .env, or switch "
                "generation to another provider with LLM_PROVIDER=gemini|ollama."
            )

        payload: dict = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        # Omitted unless someone asked for one — see claude_temperature in config.py. Sending
        # `temperature: 0` to a Claude 5 model is a 400, not a no-op.
        chosen = self.temperature if temperature is None else temperature
        if chosen is not None:
            payload["temperature"] = chosen
        if system:
            payload["system"] = system  # top-level field, NOT a message with role="system"

        resp = httpx.post(
            f"{self.base_url}/v1/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": settings.anthropic_version,
                "content-type": "application/json",
            },
            json=payload,
            timeout=120.0,
        )
        resp.raise_for_status()
        return _claude_text(resp.json())

    # ── embeddings: Anthropic does not serve them ────────────────────────
    @property
    def embed_dim(self) -> int:
        raise NotImplementedError(_CLAUDE_NO_EMBED)

    def embed_many(self, texts: list[str], *, is_query: bool = False) -> list[list[float]]:
        raise NotImplementedError(_CLAUDE_NO_EMBED)


_CLAUDE_NO_EMBED = (
    "Anthropic serves no embedding model — set EMBEDDING_PROVIDER=gemini or ollama."
)


def _claude_text(body: dict) -> str:
    """Concatenated text blocks of the reply. Empty string when the model returned no text
    block (e.g. stop_reason with no content) — callers already treat empty output as a refusal,
    matching _gemini_text above."""
    return "".join(
        block.get("text", "")
        for block in (body.get("content") or [])
        if block.get("type") == "text"
    )


COMPLETION_PROVIDERS = {
    "ollama": OllamaProvider,
    "gemini": GeminiProvider,
    "claude": ClaudeProvider,
    "openai": OpenAIProvider,
}
# Gemini appears here as a DIFFERENT class from its completion entry (see GeminiEmbeddingProvider).
# Claude is absent because Anthropic serves no embedding model.
EMBEDDING_PROVIDERS = {
    "ollama": OllamaProvider,
    "gemini": GeminiEmbeddingProvider,
    "openai": OpenAIProvider,
}


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

    def embed(self, text: str, *, is_query: bool = False) -> list[float]:
        return self.embed_many([text], is_query=is_query)[0]

    def embed_many(self, texts: list[str], *, is_query: bool = False) -> list[list[float]]:
        """Embed a batch. `is_query=True` for a SEARCH QUERY, default False for a stored DOCUMENT.

        The default is the safe one: ingestion (the only bulk caller) embeds documents, and a
        provider that ignores the flag behaves identically either way.
        """
        if not texts:
            return []
        return self.embedding_provider.embed_many(list(texts), is_query=is_query)

    @classmethod
    def use_provider(cls, provider: LLMProvider | None) -> None:
        """Swap the backend at runtime (tests / manual override). One provider stands in for
        BOTH roles, so a single fake covers the whole facade. Pass None to revert to the
        settings-configured providers."""
        cls._override = provider
        _build_completion_provider.cache_clear()
        _build_embedding_provider.cache_clear()
