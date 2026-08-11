"""UNIT (UC4) — ReviewService with repositories replaced by mocks."""
from unittest.mock import Mock
from types import SimpleNamespace

import pytest

from app.services.review_service import ReviewService, StorageError
from app.repositories.user_repository import UserRepository

pytestmark = pytest.mark.unit


def test_reviewer_lookup_maps_the_existing_therapist(fake_supabase):
    """UC4 extension: the repository edge resolves who wrote the review."""
    therapist_id = "11111111-1111-1111-1111-111111111111"
    fake_supabase(seed={"users": [{
        "id": therapist_id, "email": "therapist@example.org", "name": "Therapist One",
    }]})

    reviewer = UserRepository().find_by_id(therapist_id)

    assert str(reviewer.id) == therapist_id
    assert reviewer.name == "Therapist One"
    assert reviewer.email == "therapist@example.org"


def test_submit_review_returns_the_stored_review():
    """UT-4.3: valid input is handed to the repository and its review returned."""
    service = ReviewService()
    service.reviews = Mock()
    service.users = Mock()
    service.users.find_by_id.return_value = None
    stored = {
        "id": "review-1", "activity_id": "activity-1",
        "therapist_id": "therapist-1", "text": "Useful.",
        "approval_status": None,
    }
    service.reviews.save.return_value = [stored]

    result = service.submit_review("activity-1", "therapist-1", "Useful.", None)

    assert result == {**stored, "reviewer": {"id": "therapist-1"}}
    service.reviews.save.assert_called_once_with({
        "activity_id": "activity-1", "therapist_id": "therapist-1",
        "text": "Useful.", "approval_status": None,
    })


def test_submit_review_translates_a_repository_failure():
    """UT-4.4: a storage failure becomes the service's StorageError contract."""
    service = ReviewService()
    service.reviews = Mock()
    service.users = Mock()
    service.reviews.save.side_effect = ConnectionError("database unavailable")

    with pytest.raises(StorageError, match="Review could not be saved"):
        service.submit_review("activity-1", "therapist-1", "Useful.", None)


@pytest.mark.parametrize("decision", ["APPROVED", "REJECTED"])
def test_submit_review_stores_the_therapist_decision(decision):
    """UC4 extension: approval is part of the review, not UC3 activity status."""
    service = ReviewService()
    service.reviews = Mock()
    service.users = Mock()
    service.users.find_by_id.return_value = SimpleNamespace(
        name="Therapist One", email="therapist@example.org",
    )
    stored = {
        "id": "review-1", "activity_id": "activity-1",
        "therapist_id": "therapist-1", "text": "Useful.",
        "approval_status": decision,
    }
    service.reviews.save.return_value = [stored]

    result = service.submit_review(
        "activity-1", "therapist-1", "Useful.", decision,
    )

    service.reviews.save.assert_called_once_with({
        "activity_id": "activity-1", "therapist_id": "therapist-1",
        "text": "Useful.", "approval_status": decision,
    })
    assert result["approval_status"] == decision
    assert result["reviewer"]["name"] == "Therapist One"


def test_list_reviews_adds_the_reviewer_identity():
    """UC4 extension: persisted reviews identify the therapist who wrote them."""
    service = ReviewService()
    service.reviews = Mock()
    service.users = Mock()
    service.reviews.find_by_activity.return_value = [{
        "activity_id": "activity-1", "therapist_id": "therapist-1",
        "text": "Useful.", "approval_status": None,
    }]
    service.users.find_by_id.return_value = SimpleNamespace(
        name="", email="therapist@example.org",
    )

    result = service.list_reviews("activity-1")

    assert result[0]["reviewer"] == {
        "id": "therapist-1", "name": "", "email": "therapist@example.org",
    }
