"""Data access for `learner_sittings` — one row per learner per semester.

The score history behind the profile page's line chart. Different grain from `learners`, which
holds one row per person with their CURRENT marks: the workbook carries ~22,892 sittings for
5,783 students across nine semesters, and the ingest writes all of them here.

TWO WRITERS, ONE TABLE:
    the ingest       `source='workbook'`, upserting the whole workbook on (learner_id, semester)
    UC1's upload     `source='upload'`, appending one sitting when a therapist confirms

`upsert_many` is the contract between them. Whichever wrote last, `latest_for_learner` finds the
newest and ProfilingService promotes it onto the learner — so an uploaded assessment reaches the
dashboard through exactly the same path a workbook row does.
"""
from app.repositories.base import BaseRepository

# PostgREST's per-request row cap, and Supabase's payload limit. Same values and same reasons as
# LearnerRepository — a read that must be complete pages, a write that is large batches.
PAGE = 1000
BATCH = 500

# Every column the chart and the promotion need. Not `*`: the ingest writes ~22,892 rows and the
# reads are per learner, so the shape is small either way, but naming it keeps the two callers
# honest about what a sitting actually carries.
SITTING_COLUMNS = (
    "id,learner_id,semester,band,band_group,source,"
    "phonics,word_reading_accuracy,word_spelling,writing,writing_genre,"
    "phonics_pct,word_reading_accuracy_pct,word_spelling_pct,writing_pct"
)


class LearnerSittingRepository(BaseRepository):
    table = "learner_sittings"

    def list_by_learner(self, learner_id: str) -> list[dict]:
        """One learner's whole history, OLDEST FIRST — the order the chart plots left to right.

        `semester` sorts chronologically as plain text ('2022 Sem 1' < '2022 Sem 2' <
        '2023 Sem 1'), which holds for every value in the workbook; see dial_workbook. No paging:
        a learner has at most ten sittings, far inside the row cap.
        """
        return (
            self.db.select(SITTING_COLUMNS)
                   .eq("learner_id", learner_id)
                   .order("semester")
                   .execute().data
        ) or []

    def latest_for_learner(self, learner_id: str) -> dict | None:
        """The most recent sitting, or None when the learner has never been assessed.

        None is what turns into the upload prompt on the profile page, so it is an ordinary
        answer rather than an error: an app-created learner has no sittings until UC1 adds one.
        """
        rows = (
            self.db.select(SITTING_COLUMNS)
                   .eq("learner_id", learner_id)
                   .order("semester", desc=True)
                   .limit(1)
                   .execute().data
        ) or []
        return rows[0] if rows else None

    def upsert_many(self, rows: list[dict], batch: int = BATCH) -> int:
        """Bulk write, conflicting on (learner_id, semester).

        NOT on the primary key: `id` is generated, so conflicting on it would append a duplicate
        sitting on every re-ingest and the chart would show ten points where there is one
        semester. The pair is the natural key — a learner sits a given semester once.
        """
        for start in range(0, len(rows), batch):
            self.db.upsert(
                rows[start:start + batch], on_conflict="learner_id,semester"
            ).execute()
        return len(rows)

    def count(self) -> int:
        """How many sittings are stored, without transferring them — the ingest's audit line.

        `count="exact"` + `.limit(1)`, not `head=True`: the latter reads better but does not
        exist in postgrest 0.16.11, which is what `supabase==2.7.4` pins. PostgREST counts the
        whole set regardless of the limit, so one row on the wire still gives the true total.
        """
        return self.db.select("id", count="exact").limit(1).execute().count or 0
