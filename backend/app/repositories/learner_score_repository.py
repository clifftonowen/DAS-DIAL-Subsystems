"""Data access for the anonymised DAS cohort and its clustering runs (Subsystem 2)."""
from app.repositories.base import BaseRepository

# PostgREST caps a single select at 1,000 rows. The cohort is ~5,800, so an unpaged
# `select("*")` returns 1,000 of them WITHOUT erroring — the dashboard would just quietly plot
# a sixth of the cohort. Every read here pages.
PAGE = 1000

# Upserts go up in batches: one 5,783-row request exceeds Supabase's payload limit.
BATCH = 500

# Only what the scatter, its table and its legend actually need. The cohort is thousands of
# rows, so every unused column is multiplied by 5,783 on the wire.
COHORT_COLUMNS = (
    "student_id,learner_id,band,band_group,cluster_band,cluster_cohort,writing_genre,"
    "phonics,word_reading_accuracy,word_spelling,writing"
)


class LearnerScoreRepository(BaseRepository):
    table = "learner_scores"

    def list_cohort(self) -> list[dict]:
        """Every student, paged. Ordered by student_id so the pages cannot overlap or skip:
        without a stable sort PostgREST may return rows in a different order per request."""
        rows: list[dict] = []
        offset = 0
        while True:
            page = (
                self.db.select(COHORT_COLUMNS)
                       .order("student_id")
                       .range(offset, offset + PAGE - 1)
                       .execute().data
            ) or []
            rows.extend(page)
            if len(page) < PAGE:
                return rows
            offset += PAGE

    def upsert_many(self, rows: list[dict], batch: int = BATCH) -> int:
        for start in range(0, len(rows), batch):
            self.db.upsert(rows[start:start + batch]).execute()
        return len(rows)

    def delete_all(self) -> None:
        """Clear the cohort before a reload. `neq` on the primary key is how PostgREST spells
        "match every row" — it refuses an unfiltered delete, by design."""
        self.db.delete().neq("student_id", "").execute()


class ClusteringRunRepository(BaseRepository):
    table = "clustering_runs"

    def save_many(self, runs: list[dict]) -> int:
        self.db.insert(runs).execute()
        return len(runs)

    def latest_by_scope_and_tier(self) -> list[dict]:
        """The newest run for each (scope, tier) — the cohort model plus one per band group.

        Ingest appends rather than overwrites, so older fits stay inspectable in the table and
        the de-duplication happens here. Rows arrive newest-first, so the first sighting of a
        key is the one to keep.

        Keyed on the pair, not on tier alone: the two scopes are separate models and a future
        scope could reuse a tier name. Ordered cohort-first, then bands alphabetically, which
        is the order the dashboard's comparison caption reads in.
        """
        rows = self.db.select("*").order("created_at", desc=True).execute().data or []
        newest: dict[tuple, dict] = {}
        for row in rows:
            newest.setdefault((row.get("scope"), row.get("tier")), row)
        return [
            newest[key]
            for key in sorted(newest, key=lambda k: (k[0] != "cohort", str(k[0]), str(k[1])))
        ]
