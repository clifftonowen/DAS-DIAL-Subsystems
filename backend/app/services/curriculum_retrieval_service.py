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
        band_group: str | None = None,
        concept: str | None = None,
        stage: str | None = None,
        k: int = 3,
        vector_only: bool = False,
    ) -> list[dict]:
        """Retrieve grounding chunks. Hybrid (vector + full-text, RRF) by default; pass
        vector_only=True for pure semantic ranking (A/B comparison / fallback).

        `band` is exact ('A1'); `band_group` is the letter ('A') and is how a LEARNER is scoped —
        it reaches the unlevelled chunks and the band books together. Both stay optional here on
        purpose: the CLI explores the corpus with no learner in hand. Making band scope mandatory
        is ActivityGenerationService's job, one layer up, where a learner exists to scope to.
        """
        vector = self.llm.embed(query)  # 768-dim, active embedding provider (Ollama)
        try:
            if vector_only:
                return self.repo.match_curriculum(
                    vector, band=band, band_group=band_group,
                    concept=concept, stage=stage, match_count=k,
                )
            return self.repo.hybrid_match_curriculum(
                vector, query, band=band, band_group=band_group,
                concept=concept, stage=stage, match_count=k,
            )
        except Exception:
            return []  # empty corpus / filter miss / Supabase unreachable during dev
