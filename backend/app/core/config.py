"""Central configuration loaded from environment (.env)."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Supabase
    supabase_url: str = ""
    supabase_key: str = ""          # service-role key, backend only
    supabase_jwt_secret: str = ""   # used to verify auth tokens

    # LLM — swap the whole backend by changing llm_provider ("ollama" | "openai")
    llm_provider: str = "ollama"

    # OpenAI backend
    openai_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"

    # Ollama backend (local; run `ollama serve`)
    ollama_base_url: str = "http://localhost:11434"
    ollama_llm_model: str = "llama3.2:latest"
    ollama_embedding_model: str = "nomic-embed-text:latest"
    ollama_embedding_dim: int = 768  # nomic-embed-text; matches vector(768) for curriculum_chunks

    # App
    app_name: str = "DAS D.I.A.L"
    cors_origins: str = "http://localhost:5173"


settings = Settings()
