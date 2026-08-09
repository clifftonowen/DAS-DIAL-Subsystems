from app.repositories.base import BaseRepository, StorageError


class AssessmentRepository(BaseRepository):
    table = "assessment_records"

    def save(self, record: dict) -> dict:
        return self.db.upsert(record).execute().data

    def find_by_learner(self, learner_id: str) -> list[dict]:
        """A learner's assessment records, newest sitting first.

        An unreachable database raises StorageError (UT-2.7) rather than letting the
        driver's own exception escape. An empty result is NOT an error here — "this learner
        has no records" is a fact the caller acts on, and ProfilingService turns it into
        EmptyDataError. Conflating the two would report a network outage as a learner with
        no data, and the therapist would be told to upload an assessment that already exists.
        """
        try:
            rows = (
                self.db.select("*")
                       .eq("learner_id", learner_id)
                       .order("assessment_date", desc=True)
                       .execute().data
            )
        except Exception as exc:
            raise StorageError(f"Could not read assessment records: {exc}") from exc
        return rows or []
