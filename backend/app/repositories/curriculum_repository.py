"""CurriculumRepository - Supabase access for the curriculum_chunks corpus
(Subsystem 3 RAG exemplars). Distinct from KnowledgeBaseRepository's
instructional_strategies corpus and from learning_activities."""
from app.repositories.base import BaseRepository


class CurriculumRepository(BaseRepository):
    table = "curriculum_chunks"

    def delete_by_source(self, source_file: str) -> None:
        """Wipe a source's chunks before re-inserting -> idempotent ingestion."""
        self.db.delete().eq("source_file", source_file).execute()

    def upsert_chunks(self, rows: list[dict]) -> list[dict]:
        """Insert/replace a batch of chunk rows (already serialised to dicts)."""
        if not rows:
            return []
        return self.db.upsert(rows).execute().data

    def count_by_band_group(self, band_group: str) -> int:
        """How many lesson-plan chunks exist for a band LETTER, without transferring them.

        Only called on the refusal path, to tell "no curriculum has been ingested for this band"
        apart from "the band has curriculum but nothing matched" — two very different things to
        tell a therapist. `like` rather than `eq` for the same reason as filter_band_group: band A
        is stored as 'A' plus 'A1'/'A2'/'A3'.
        """
        return (
            self.db.select("id", count="exact")
            .eq("doc_type", "lesson_plan")
            .like("band", f"{band_group}%")
            .limit(1)
            .execute()
            .count or 0
        )

    def match_curriculum(
        self,
        query_vector: list[float],
        band: str | None = None,
        band_group: str | None = None,
        concept: str | None = None,
        stage: str | None = None,
        match_count: int = 3,
    ) -> list[dict]:
        """Metadata-filtered vector retrieval (pure semantic; kept for A/B + fallback)."""
        return match_curriculum_rpc(query_vector, band, band_group, concept, stage, match_count)

    def hybrid_match_curriculum(
        self,
        query_vector: list[float],
        query_text: str,
        band: str | None = None,
        band_group: str | None = None,
        concept: str | None = None,
        stage: str | None = None,
        match_count: int = 3,
        rrf_k: int = 50,
        full_text_weight: float = 1.0,
        semantic_weight: float = 1.0,
    ) -> list[dict]:
        """Hybrid retrieval: vector + full-text fused by RRF (see hybrid_match_curriculum RPC)."""
        return hybrid_match_curriculum_rpc(
            query_vector, query_text, band, band_group, concept, stage,
            match_count, rrf_k, full_text_weight, semantic_weight,
        )


def match_curriculum_rpc(query_vector, band, band_group, concept, stage, match_count):
    from app.core.supabase_client import get_supabase
    return (
        get_supabase()
        .rpc(
            "match_curriculum",
            {
                "query_embedding": query_vector,
                "filter_band": band,
                "filter_band_group": band_group,
                "filter_concept": concept,
                "filter_stage": stage,
                "match_count": match_count,
            },
        )
        .execute()
        .data
    )


def hybrid_match_curriculum_rpc(
    query_vector, query_text, band, band_group, concept, stage,
    match_count, rrf_k, full_text_weight, semantic_weight,
):
    from app.core.supabase_client import get_supabase
    return (
        get_supabase()
        .rpc(
            "hybrid_match_curriculum",
            {
                "query_embedding": query_vector,
                "query_text": query_text,
                "filter_band": band,
                "filter_band_group": band_group,
                "filter_concept": concept,
                "filter_stage": stage,
                "match_count": match_count,
                "rrf_k": rrf_k,
                "full_text_weight": full_text_weight,
                "semantic_weight": semantic_weight,
            },
        )
        .execute()
        .data
    )
