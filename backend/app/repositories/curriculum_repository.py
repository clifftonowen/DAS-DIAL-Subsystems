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

    def chunks_for_reembed(self) -> list[dict]:
        """Every lesson-plan chunk's id + persisted embed_text, for re-embedding in place.

        The point of reading `embed_text` back rather than re-running the pipeline: ingestion
        re-parses from PDF, and the PDFs are gitignored. `embed_text` is the exact string that was
        embedded (chunk_builder.build_embed_text), so re-embedding from it reproduces the document
        side byte-for-byte — which is what makes two models' scores comparable.
        """
        rows, start, page = [], 0, 1000
        while True:
            batch = (
                self.db.select("id,embed_text")
                .eq("doc_type", "lesson_plan")
                .range(start, start + page - 1)
                .execute()
                .data
            )
            rows.extend(batch)
            if len(batch) < page:
                return rows
            start += page

    def set_embedding(self, chunk_id: str, vector: list[float], model: str,
                      column: str = "embedding_alt") -> None:
        """Write one chunk's vector to `column` (+ its `_model` sibling), leaving the row alone.

        An UPDATE, deliberately, not delete_by_source + upsert: a full re-ingest regenerates
        `id` (gen_random_uuid()), which would silently invalidate any evaluation keyed on chunk
        identity and make before/after runs incomparable.
        """
        model_col = "embedding_model" if column == "embedding" else f"{column}_model"
        self.db.update({column: vector, model_col: model}).eq("id", chunk_id).execute()

    def match_curriculum(
        self,
        query_vector: list[float],
        band: str | None = None,
        band_group: str | None = None,
        concept: str | None = None,
        stage: str | None = None,
        match_count: int = 3,
        use_alt: bool = False,
    ) -> list[dict]:
        """Metadata-filtered vector retrieval (pure semantic; kept for A/B + fallback)."""
        return match_curriculum_rpc(query_vector, band, band_group, concept, stage,
                                    match_count, use_alt)

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
        use_alt: bool = False,
    ) -> list[dict]:
        """Hybrid retrieval: vector + full-text fused by RRF (see hybrid_match_curriculum RPC)."""
        return hybrid_match_curriculum_rpc(
            query_vector, query_text, band, band_group, concept, stage,
            match_count, rrf_k, full_text_weight, semantic_weight, use_alt,
        )


def _with_alt(params: dict, use_alt: bool) -> dict:
    """Add `use_alt` to an RPC payload ONLY when it is on.

    PostgREST resolves overloads by the exact set of argument names supplied, so sending
    `use_alt: false` to a database that has not run 2026-08-10_curriculum_embedding_alt.sql yet
    fails with PGRST202 — and CurriculumRetrievalService swallows that into an empty result,
    which reads as "nothing matched" rather than "your schema is behind". Omitting the default
    keeps every production path working against BOTH schema versions, so only the evaluation
    harness (the one caller that passes true) actually requires the migration.
    """
    return {**params, "use_alt": True} if use_alt else params


def match_curriculum_rpc(query_vector, band, band_group, concept, stage, match_count,
                         use_alt=False):
    from app.core.supabase_client import get_supabase
    return (
        get_supabase()
        .rpc(
            "match_curriculum",
            _with_alt(
                {
                    "query_embedding": query_vector,
                    "filter_band": band,
                    "filter_band_group": band_group,
                    "filter_concept": concept,
                    "filter_stage": stage,
                    "match_count": match_count,
                },
                use_alt,
            ),
        )
        .execute()
        .data
    )


def hybrid_match_curriculum_rpc(
    query_vector, query_text, band, band_group, concept, stage,
    match_count, rrf_k, full_text_weight, semantic_weight, use_alt=False,
):
    from app.core.supabase_client import get_supabase
    return (
        get_supabase()
        .rpc(
            "hybrid_match_curriculum",
            _with_alt(
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
                use_alt,
            ),
        )
        .execute()
        .data
    )
