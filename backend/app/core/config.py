"""Central configuration loaded from environment (.env)."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Supabase
    supabase_url: str = ""
    supabase_key: str = ""          # service-role key, backend only
    supabase_jwt_secret: str = ""   # used to verify auth tokens

    # LLM — completion and embedding are selected SEPARATELY, so generation can move to a hosted
    # model while embeddings stay local. Embedding defaults to ollama and should stay there:
    # curriculum_chunks is vector(768) (nomic-embed-text) and activity_prompts.MIN_SIMILARITY is
    # tuned to that model's score band, so changing it silently invalidates both.
    llm_provider: str = "ollama"          # completion: "ollama" | "gemini" | "openai"
    embedding_provider: str = "ollama"    # embeddings: "ollama" | "openai"

    # Gemini backend (generation only — Gemini embeddings are deliberately not wired)
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-pro"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_temperature: float = 0.0

    # OpenAI backend
    openai_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"

    # Ollama backend (local; run `ollama serve`)
    ollama_base_url: str = "http://localhost:11434"
    ollama_llm_model: str = "llama3.2:latest"
    ollama_embedding_model: str = "nomic-embed-text:latest"
    ollama_embedding_dim: int = 768  # nomic-embed-text; matches vector(768) for curriculum_chunks

    # Generation sampling — temperature 0 + fixed seed = reproducible output (same input -> same activity)
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
