"""ReviewService — store a therapist's review and read them back."""
from app.repositories.review_repository import ReviewRepository
from app.repositories.activity_repository import ActivityRepository

class StorageError(Exception):
    "The database rejected the review."

class ReviewService:
    def __init__(self):
        self.reviews = ReviewRepository()
        self.activities = ActivityRepository()

    def submit_review(self, activity_id: str, therapist_id: str, text: str, status) -> dict:
        review = {"activity_id": activity_id, "therapist_id": therapist_id, "text": text}
        try:
            stored = self.reviews.save(review)[0]
        except Exception as exc:
            raise StorageError("Review could not be saved") from exc
 
        if status:
            self.activities.set_status(activity_id, status)
            stored = {**stored, "activity_status": status}
 
        return stored


    def list_reviews(self, activity_id: str) -> list[dict]:
        return self.reviews.find_by_activity(activity_id)


