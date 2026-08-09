"""Central configuration loaded from environment (.env)."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Supabase
    supabase_url: str = ""
    supabase_key: str = ""
    supabase_jwt_secret: str = ""

    # LLM — completion and embedding are selected SEPARATELY, so the generator can move between
    # vendors freely while the embedder (the expensive one to change) stays put.
    #
    # What changing the EMBEDDING provider actually costs, now that Matryoshka models can output
    # 768 dims to match curriculum_chunks: not a migration, but still a full re-embed AND a
    # re-derived `min_similarity` below — every model has its own score band, and a gate tuned to
    # one model's band silently refuses (or admits) the wrong things on another's.
    llm_provider: str = "ollama"          # completion: "ollama" | "gemini" | "claude" | "openai"
    embedding_provider: str = "ollama"    # embeddings: "ollama" | "gemini" | "openai"

    # Retrieval gate: top-chunk cosine similarity below this => refuse without calling the LLM.
    # PROVIDER-SPECIFIC, which is why it is a setting and not a constant — two people evaluating
    # two embedders need two values at once. Derive it with scripts/calibrate_gate.py; never guess.
    # Default 0.50 is nomic-embed-text's (junk lands ~0.42, real matches 0.58+).
    min_similarity: float = 0.50

    # Gemini backend — generation and embedding are separate classes with separate models.
    gemini_api_key: str = ""
    # gemini-2.5-pro is listed by the models endpoint but 404s on generateContent for keys
    # issued after it closed to new users — pick a model, then verify it actually answers.
    gemini_model: str = "gemini-3.5-flash"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_temperature: float = 0.0

    # NOT gemini-embedding-2, despite it being the newer model. Measured on this corpus
    # (240 probes, backend/eval/): -001 scores MRR 0.697 / recall@1 0.533 against -2's
    # 0.613 / 0.429, and separates junk from real queries nearly twice as widely. The cause is
    # concrete, not noise — -2 accepts `taskType` and ignores it (RETRIEVAL_QUERY and
    # RETRIEVAL_DOCUMENT return bit-identical vectors), so it cannot embed a query differently
    # from a document, and this is an asymmetric retrieval task. -2's one advantage, an 8192-token
    # window against -001's 2048, buys nothing here: the largest chunk in the corpus is ~1561.
    gemini_embedding_model: str = "gemini-embedding-001"
    gemini_embedding_dim: int = 768   # Matryoshka truncation; matches vector(768), no migration

    # Anthropic backend (generation only — Anthropic serves no embedding model)
    anthropic_api_key: str = ""
    anthropic_base_url: str = "https://api.anthropic.com"
    anthropic_version: str = "2023-06-01"
    claude_model: str = "claude-sonnet-5"
    # None => omit the field entirely, which is REQUIRED on the Claude 5 family: they reject
    # `temperature` outright ("`temperature` is deprecated for this model", HTTP 400) rather than
    # ignoring it. Set a float only for an older model that still accepts one. Note this means
    # Claude has no temperature-0 lever at all, so it cannot offer even Gemini's weak determinism.
    claude_temperature: float | None = None
    # REQUIRED by the Messages API — there is no "unlimited". Sized for a full activity with
    # room to spare; a too-small cap truncates mid-step and reads downstream as a short activity,
    # not as an error.
    claude_max_tokens: int = 4096

    # OpenAI backend
    openai_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"

    # Ollama backend (local; run `ollama serve`)
    ollama_base_url: str = "http://localhost:11434"
    ollama_llm_model: str = "llama3.2:latest"
    ollama_embedding_model: str = "nomic-embed-text:latest"
    ollama_embedding_dim: int = 768  # nomic-embed-text; matches vector(768) for curriculum_chunks
    # nomic-embed-text is TRAINED to expect "search_query: " / "search_document: " prefixes and
    # retrieval is measurably worse without them — but the stored corpus was embedded without, so
    # turning this on alone pairs prefixed queries against unprefixed documents and makes things
    # WORSE. Flip it and re-embed in the same change, or leave it alone.
    ollama_use_task_prefixes: bool = False

    # Generation sampling. Temperature 0 + fixed seed is reproducible ON OLLAMA ONLY: Gemini
    # treats seed as best-effort and only when explicitly passed, and Claude has no seed at all.
    ollama_temperature: float = 0.0
    ollama_seed: int = 42

    # App
    app_name: str = "DAS D.I.A.L"
    # Comma-separated browser origins allowed to call the API. Since the UI signs in
    # through AuthController rather than talking to Supabase directly, log-in itself
    # is now a cross-origin request, so an origin missing here breaks authentication
    # outright — the browser rejects the response and fetch fails with
    # "Failed to fetch", with no status for the UI to report.
    #
    # An origin is scheme + host + port, and localhost is NOT the same origin as
    # 127.0.0.1, so both spellings of both ports are listed: 5173 is `npm run dev`,
    # 4173 is `npm run preview` (the built app the Selenium system tests drive).
    cors_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:4173,http://127.0.0.1:4173"
    )

    #smtp for email 
    email_enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_use_tls: bool = True


settings = Settings()
