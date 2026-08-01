from app.repositories.base import BaseRepository


class ReviewRepository(BaseRepository):
    table = "reviews"

    def save(self, review: dict) -> dict:
        return self.db.upsert(review).execute().data

    def find_by_activity(self, activity_id: str) -> list[dict]:
        return self.db.select("*").eq("activity_id", activity_id).order("created_at", desc=True).execute().data
