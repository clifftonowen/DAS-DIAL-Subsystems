from app.repositories.review_repository import ReviewRepository


class ReviewService:
    def __init__(self):
        self.reviews = ReviewRepository()

    def submit_review(self, activity_id: str, therapist_id: str, text: str) -> dict:
        review = {"activity_id": activity_id, "therapist_id": therapist_id, "text": text}
        self.reviews.save(review)
        return review
