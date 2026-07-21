"""LLMApiClient - single wrapper over the LLM for completion + embedding.

Agents depend on this so the model can be swapped in one place.
"""
from functools import lru_cache
from app.core.config import settings

EMBED_DIM = 1536  # text-embedding-3-small; must match vector(1536) in schema.sql


class LLMApiClient:
    def complete(self, prompt: str) -> str:
        # TODO: call langchain-openai ChatOpenAI(model=settings.llm_model)
        return f"[stub completion for prompt of {len(prompt)} chars]"

    def embed(self, text: str) -> list[float]:
        return self.embed_many([text])[0]

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        """Batch-embed via OpenAI (langchain-openai). Falls back to zero-vectors when no API
        key is configured, so the app stays bootable in dev and dry-run paths never need one."""
        if not texts:
            return []
        if not settings.openai_api_key:
            return [[0.0] * EMBED_DIM for _ in texts]
        return _embeddings().embed_documents(list(texts))


@lru_cache
def _embeddings():
    from langchain_openai import OpenAIEmbeddings  # lazy: package/key only needed for real embed
    return OpenAIEmbeddings(model=settings.embedding_model, api_key=settings.openai_api_key)
