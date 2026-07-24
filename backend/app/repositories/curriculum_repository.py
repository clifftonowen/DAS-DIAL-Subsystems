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

    def match_curriculum(
        self,
        query_vector: list[float],
        band: str | None = None,
        concept: str | None = None,
        stage: str | None = None,
        match_count: int = 3,
    ) -> list[dict]:
        """Metadata-filtered vector retrieval (used later by the retrieval layer)."""
        return match_curriculum_rpc(query_vector, band, concept, stage, match_count)


def match_curriculum_rpc(query_vector, band, concept, stage, match_count):
    from app.core.supabase_client import get_supabase
    return (
        get_supabase()
        .rpc(
            "match_curriculum",
            {
                "query_embedding": query_vector,
                "filter_band": band,
                "filter_concept": concept,
                "filter_stage": stage,
                "match_count": match_count,
            },
        )
        .execute()
        .data
    )
