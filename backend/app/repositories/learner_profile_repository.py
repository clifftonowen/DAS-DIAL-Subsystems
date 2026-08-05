from app.repositories.base import BaseRepository, StorageError


class LearnerProfileRepository(BaseRepository):
    table = "learner_profiles"

    def save(self, profile: dict) -> dict:
        """Persist a generated profile. `saveProfile()` in the UC2 sequence diagram.

        A refused or unreachable write raises StorageError (UT-2.11), which the router
        turns into a 500. The profile must NOT be reported as generated when the write
        failed — step 6a of the operational flow.
        """
        try:
            return self.db.upsert(profile).execute().data
        except Exception as exc:
            raise StorageError(f"Could not save learner profile: {exc}") from exc

    def find_by_id(self, profile_id: str) -> dict | None:
        rows = self.db.select("*").eq("id", profile_id).execute().data
        return rows[0] if rows else None

    def find_by_learner(self, learner_id: str) -> dict | None:
        rows = self.db.select("*").eq("learner_id", learner_id).order("created_at", desc=True).execute().data
        return rows[0] if rows else None

    def list_by_learner(self, learner_id: str) -> list[dict]:
        return self.db.select("*").eq("learner_id", learner_id).order("created_at", desc=True).execute().data
