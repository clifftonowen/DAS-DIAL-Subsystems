"""CurriculumRetrievalService - RAG retrieval of curriculum chunks via pgvector.

Mirrors RetrievalService (instructional_strategies corpus) but targets curriculum_chunks:
embed the query with the active provider, then rank via the match_curriculum RPC. Metadata
filters run in the RPC's WHERE (correctness); the 768-dim vector only orders survivors."""
from app.repositories.curriculum_repository import CurriculumRepository
from app.gateways.llm_client import LLMApiClient


class CurriculumRetrievalService:
    def __init__(self):
        self.repo = CurriculumRepository()
        self.llm = LLMApiClient()

    def retrieve(
        self,
        query: str,
        band: str | None = None,
        concept: str | None = None,
        stage: str | None = None,
        k: int = 3,
    ) -> list[dict]:
        vector = self.llm.embed(query)  # 768-dim, active Ollama provider
        try:
            return self.repo.match_curriculum(
                vector, band=band, concept=concept, stage=stage, match_count=k
            )
        except Exception:
            return []  # empty corpus / filter miss / Supabase unreachable during dev
