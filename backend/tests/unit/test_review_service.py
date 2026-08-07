"""UNIT (UC4) — ReviewService with repositories replaced by mocks."""
from unittest.mock import Mock

import pytest

from app.services.review_service import ReviewService, StorageError

pytestmark = pytest.mark.unit


def test_submit_review_returns_the_stored_review():
    """UT-4.3: valid input is handed to the repository and its review returned."""
    service = ReviewService()
    service.reviews = Mock()
    stored = {"id": "review-1", "activity_id": "activity-1", "therapist_id": "therapist-1", "text": "Useful."}
    service.reviews.save.return_value = [stored]

    result = service.submit_review("activity-1", "therapist-1", "Useful.", None)

    assert result == stored
    service.reviews.save.assert_called_once_with({
        "activity_id": "activity-1", "therapist_id": "therapist-1", "text": "Useful.",
    })


def test_submit_review_translates_a_repository_failure():
    """UT-4.4: a storage failure becomes the service's StorageError contract."""
    service = ReviewService()
    service.reviews = Mock()
    service.reviews.save.side_effect = ConnectionError("database unavailable")

    with pytest.raises(StorageError, match="Review could not be saved"):
        service.submit_review("activity-1", "therapist-1", "Useful.", None)
