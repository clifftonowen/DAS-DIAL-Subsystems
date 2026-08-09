from app.repositories.base import BaseRepository


class ActivityRepository(BaseRepository):
    table = "learning_activities"

    def save(self, activity: dict) -> dict:
        return self.db.upsert(activity).execute().data

    def find_by_id(self, activity_id: str) -> dict | None:
        rows = self.db.select("*").eq("id", activity_id).execute().data
        return rows[0] if rows else None

    def find_by_learner(self, learner_id: str) -> list[dict]:
        """Activities generated for one learner, newest first.

        Keyed on the learner, not a profile: `profiled -> learner_profiles(id)` became
        `learner_id -> learners(id)` when the profile stopped being a separate row.
        """
        return (
            self.db.select("*").eq("learner_id", learner_id)
                   .order("created_at", desc=True).execute().data
        )

    def set_status(self, activity_id: str, status: str) -> dict | None:
        rows = self.db.update({"status": status}).eq("id", activity_id).execute().data
        return rows[0] if rows else None

