"""Central configuration loaded from environment (.env)."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Supabase
    supabase_url: str = ""
    supabase_key: str = ""          # service-role key, backend only
    supabase_jwt_secret: str = ""   # used to verify auth tokens

    # LLM
    openai_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"

    # App
    app_name: str = "DAS D.I.A.L"
    cors_origins: str = "http://localhost:5173"


settings = Settings()
