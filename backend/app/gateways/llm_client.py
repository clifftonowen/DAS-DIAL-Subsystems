"""LLMApiClient - single wrapper over the LLM for completion + embedding.

Agents depend on this so the model can be swapped in one place.
"""
from app.core.config import settings


class LLMApiClient:
    def complete(self, prompt: str) -> str:
        # TODO: call langchain-openai ChatOpenAI(model=settings.llm_model)
        return f"[stub completion for prompt of {len(prompt)} chars]"

    def embed(self, text: str) -> list[float]:
        # TODO: real embeddings (dim must match schema, default 1536)
        return [0.0] * 1536
