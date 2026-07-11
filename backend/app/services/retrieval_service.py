"""RetrievalService - RAG retrieval of instructional strategies via pgvector."""
from app.repositories.knowledge_base_repository import KnowledgeBaseRepository
from app.gateways.llm_client import LLMApiClient


class RetrievalService:
    def __init__(self):
        self.kb = KnowledgeBaseRepository()
        self.llm = LLMApiClient()

    def retrieve_strategies(self, profile_metrics: dict, k: int = 5) -> list[dict]:
        query = " ".join(f"{key}:{val}" for key, val in profile_metrics.items())
        vector = self.llm.embed(query)
        try:
            return self.kb.similarity_search(vector, k)
        except Exception:
            return []  # empty corpus during early dev
