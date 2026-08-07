"""UNIT (UC4) — ReviewRepository, with only its database driver replaced."""
import pytest

from app.repositories.review_repository import ReviewRepository

pytestmark = pytest.mark.unit


def test_save_stores_and_returns_a_review(fake_supabase):
    """UT-4.1: a reachable database stores a valid review."""
    fake = fake_supabase(seed={"reviews": []})
    review = {"activity_id": "activity-1", "therapist_id": "therapist-1", "text": "Useful."}

    saved = ReviewRepository().save(review)

    assert saved == [review]
    assert fake.store["reviews"] == [review]


def test_save_propagates_a_database_failure(monkeypatch):
    """UT-4.2: the repository does not turn a driver failure into a success."""
    class UnreachableDatabase:
        def upsert(self, _review):
            raise ConnectionError("database unavailable")

    monkeypatch.setattr(ReviewRepository, "db", property(lambda _self: UnreachableDatabase()))

    with pytest.raises(ConnectionError, match="database unavailable"):
        ReviewRepository().save({"activity_id": "activity-1", "text": "Useful."})
