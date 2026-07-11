from app.repositories.base import BaseRepository


class ActivityRepository(BaseRepository):
    table = "learning_activities"

    def save(self, activity: dict) -> dict:
        return self.db.upsert(activity).execute().data

    def find_by_id(self, activity_id: str) -> dict | None:
        rows = self.db.select("*").eq("id", activity_id).execute().data
        return rows[0] if rows else None
