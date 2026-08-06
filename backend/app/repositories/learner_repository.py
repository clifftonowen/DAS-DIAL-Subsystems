"""Data access for `learners` — every learner, of both kinds, in one table.

    on_caseload = true    the therapist's own learners: a pseudonym, a tier, and the only ones
                          with assessment records and generated activities
    on_caseload = false   the anonymised DAS research cohort behind the analytics scatter
                          (~5,783 rows), identified only by `student_id`

These were two tables joined by a nullable self-FK; see
infra/migrations/2026-08-07_merge_learner_scores.sql for why they are one.

THE TABLE IS LARGE, AND THAT SHAPES EVERY READ HERE. PostgREST caps a single select at 1,000
rows and TRUNCATES WITHOUT ERRORING — a bare `select("*")` returns a sixth of the cohort and
looks like missing data, not like a bug. So:

    * every full read pages (`list_cohort`)
    * every total is a `count`, never `len(rows)`
    * anything user-facing is a `list_page`

There is deliberately no `delete_all()`. `learner_sittings`, `assessment_records` and
`learning_activities` all hang off this table, so an ingest-triggered delete could destroy a
learner's whole score history along with generated clinical work.
"""
from app.repositories.base import BaseRepository

# PostgREST's own per-request row cap. Reads that must be complete loop in pages of this size.
PAGE = 1000

# Upserts go up in batches: one 5,783-row request exceeds Supabase's payload limit.
BATCH = 500

# Only what the scatter, its table and its legend need. Multiplied by ~5,783 on the wire, so
# every unused column costs real bytes — `select("*")` here would carry the genre provenance
# columns and every percentile for nothing.
COHORT_COLUMNS = (
    "id,student_id,pseudonym,on_caseload,band,band_group,cluster_band,cluster_cohort,"
    "writing_genre,phonics,word_reading_accuracy,word_spelling,writing"
)

# The Learners tab's card grid. Narrower than `*` for the same reason, wider than COHORT_COLUMNS
# because the card shows a tier.
LIST_COLUMNS = "id,student_id,pseudonym,tier,on_caseload,band,band_group,cluster_cohort"

# Columns the free-text search looks in. `band` is here because "A2" is a natural thing to type;
# `pseudonym` is empty for cohort rows, and `student_id` is null for app-created ones, which is
# why the search has to span all three rather than pick one.
SEARCH_COLUMNS = ("pseudonym", "student_id", "band")


class LearnerRepository(BaseRepository):
    table = "learners"

    # ── writes ────────────────────────────────────────────────────────────
    def save(self, learner: dict) -> dict:
        return self.db.upsert(learner).execute().data

    def upsert_many(self, rows: list[dict], batch: int = BATCH) -> int:
        """Bulk upsert from the DIAL workbook, conflicting on `student_id`.

        NOT on the primary key: `id` is a uuid the workbook has never heard of, so every ingest
        would insert a fresh row and the cohort would double in size on each run. `student_id`
        is the workbook's own stable key and is unique here for exactly this purpose.

        The caller must send ONLY workbook-derived columns. PostgREST updates the columns a
        payload carries and leaves the rest alone, so omitting `pseudonym`, `tier` and
        `on_caseload` is what keeps a re-ingest from erasing the caseload identity of a learner
        who is also in the cohort. See scripts/ingest_dial_data.STORED.
        """
        for start in range(0, len(rows), batch):
            self.db.upsert(rows[start:start + batch], on_conflict="student_id").execute()
        return len(rows)

    # ── reads ─────────────────────────────────────────────────────────────
    def find_by_id(self, learner_id: str) -> dict | None:
        rows = self.db.select("*").eq("id", learner_id).execute().data
        return rows[0] if rows else None

    def find_by_student_id(self, student_id: str) -> dict | None:
        rows = self.db.select("*").eq("student_id", student_id).limit(1).execute().data
        return rows[0] if rows else None

    def count(self, *, caseload_only: bool = False) -> int:
        """How many learners, without transferring them.

        `head=True` asks PostgREST for the count header and no body. The dashboard used to do
        `len(list_all())`, which both moved the whole table and — past 1,000 rows — reported the
        cap instead of the truth.
        """
        query = self.db.select("id", count="exact", head=True)
        if caseload_only:
            query = query.eq("on_caseload", True)
        return query.execute().count or 0

    def list_page(
        self,
        *,
        limit: int = 24,
        offset: int = 0,
        query: str | None = None,
        caseload_only: bool = False,
    ) -> tuple[list[dict], int]:
        """One page of learners, plus the total matching the same filters.

        The total is of the FILTERED set, not the table, so the pager can say "1-24 of 137" for
        a search. Ordered so paging is stable: caseload first (the therapist's own learners lead
        the list), then by name, then by student id for the unnamed cohort rows.
        """
        total = self._filtered(
            self.db.select("id", count="exact", head=True), query, caseload_only
        ).execute().count or 0

        rows = (
            self._filtered(self.db.select(LIST_COLUMNS), query, caseload_only)
            # Three keys, applied in order: the therapist's own learners lead the list, then
            # alphabetical, then student id for the unnamed cohort rows so paging is stable.
            # postgrest composes repeated order() calls into one comma-separated clause.
            .order("on_caseload", desc=True)
            .order("pseudonym")
            .order("student_id")
            .range(offset, offset + limit - 1)
            .execute().data
        ) or []
        return rows, total

    def list_cohort(self) -> list[dict]:
        """Every learner, paged — the analytics scatter's single read.

        Ordered by id so the pages cannot overlap or skip: without a stable sort PostgREST may
        return rows in a different order per request, and the loop would silently lose some.
        """
        rows: list[dict] = []
        offset = 0
        while True:
            page = (
                self.db.select(COHORT_COLUMNS)
                       .order("id")
                       .range(offset, offset + PAGE - 1)
                       .execute().data
            ) or []
            rows.extend(page)
            if len(page) < PAGE:
                return rows
            offset += PAGE

    # ── helpers ───────────────────────────────────────────────────────────
    @staticmethod
    def _filtered(builder, query: str | None, caseload_only: bool):
        """Apply the search and caseload filters to an ALREADY-SELECTED builder.

        Takes the builder rather than making one, because postgrest only exposes filters after
        `.select()` — `table().eq(...)` does not exist. Called twice per page (once for the
        count, once for the rows) so the two cannot drift apart.
        """
        if caseload_only:
            builder = builder.eq("on_caseload", True)
        text = (query or "").strip()
        if text:
            # One `or_` across the three columns: a caseload learner matches on pseudonym, a
            # cohort student on student_id, and either on band. PostgREST's wildcard is `*`, and
            # a `,` or `.` inside the term would be parsed as or_() syntax, so both are stripped
            # — this is the injection boundary for user-typed search text.
            safe = text.replace(",", " ").replace(".", " ").replace("*", "").replace("(", "")
            builder = builder.or_(",".join(f"{c}.ilike.*{safe}*" for c in SEARCH_COLUMNS))
        return builder
