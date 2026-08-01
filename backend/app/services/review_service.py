"""ReviewService — store a therapist's review and read them back."""
from app.repositories.review_repository import ReviewRepository

class StorageError(Exception):
    "The database rejected the review."

class ReviewService:
    def __init__(self):
        self.reviews = ReviewRepository()

    def submit_review(self, activity_id: str, therapist_id: str, text: str) -> dict:
        review = {"activity_id": activity_id, "therapist_id": therapist_id, "text": text}
        try:
            saved = self.reviews.save(review)
        except Exception as exc:  
            raise StorageError("Review could not be saved") from exc

        if not saved:
            raise StorageError("Review could not be saved")

        return saved[0] if isinstance(saved, list) else saved

    def list_reviews(self, activity_id: str) -> list[dict]:
        return self.reviews.find_by_activity(activity_id)