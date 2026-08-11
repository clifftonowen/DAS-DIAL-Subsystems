"""ReviewService — store a therapist's review and read them back."""
from app.repositories.review_repository import ReviewRepository
from app.repositories.user_repository import UserRepository

class StorageError(Exception):
    "The database rejected the review."

class ReviewService:
    def __init__(self):
        self.reviews = ReviewRepository()
        self.users = UserRepository()

    def submit_review(
        self, activity_id: str, therapist_id: str, text: str,
        approval_status: str | None,
    ) -> dict:
        review = {
            "activity_id": activity_id,
            "therapist_id": therapist_id,
            "text": text,
            "approval_status": approval_status,
        }
        try:
            stored = self.reviews.save(review)[0]
        except Exception as exc:
            print("REVIEW SAVE FAILED:", repr(exc)) 
            raise StorageError("Review could not be saved") from exc
 
        return self._with_reviewer(stored)


    def list_reviews(self, activity_id: str) -> list[dict]:
        return [self._with_reviewer(review)
                for review in self.reviews.find_by_activity(activity_id)]

    def _with_reviewer(self, review: dict) -> dict:
        """Attach a display identity without making review storage depend on it."""
        therapist_id = review.get("therapist_id")
        reviewer = {"id": therapist_id}
        try:
            therapist = self.users.find_by_id(therapist_id)
        except Exception:
            therapist = None
        if therapist is not None:
            reviewer.update({"name": therapist.name, "email": therapist.email})
        return {**review, "reviewer": reviewer}


