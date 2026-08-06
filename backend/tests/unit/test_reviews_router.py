"""UNIT (UC4) — /reviews controller with the ReviewService replaced."""
from unittest.mock import Mock

import pytest

from app.routers import reviews as reviews_router
from app.services.review_service import StorageError

pytestmark = pytest.mark.unit


def test_submit_review_returns_the_service_review(client, auth_ok, monkeypatch):
    """UT-4.5: an authenticated request reaches the service with its therapist id."""
    submit = Mock(return_value={"id": "review-1", "text": "Useful."})
    monkeypatch.setattr(reviews_router.svc, "submit_review", submit)

    response = client.post("/reviews", json={"activity_id": "activity-1", "text": "Useful."})

    assert response.status_code == 200
    assert response.json() == {"id": "review-1", "text": "Useful."}
    submit.assert_called_once_with("activity-1", auth_ok, "Useful.", None)


def test_submit_review_rejects_blank_text_before_the_service(client, auth_ok, monkeypatch):
    """UT-4.6: an empty review is invalid input, so no review is saved."""
    submit = Mock()
    monkeypatch.setattr(reviews_router.svc, "submit_review", submit)

    response = client.post("/reviews", json={"activity_id": "activity-1", "text": "   "})

    assert response.status_code == 422
    assert "Review text must not be empty" in response.text
    submit.assert_not_called()


def test_submit_review_requires_an_authenticated_therapist(client, monkeypatch):
    """UT-4.7: without a session the service is never invoked."""
    submit = Mock()
    monkeypatch.setattr(reviews_router.svc, "submit_review", submit)

    response = client.post("/reviews", json={"activity_id": "activity-1", "text": "Useful."})

    assert response.status_code in (401, 403)
    submit.assert_not_called()


def test_submit_review_returns_a_storage_error_to_the_dashboard(client, auth_ok, monkeypatch):
    """UT-4.8: a failed save is presented as the controller's error response."""
    submit = Mock(side_effect=StorageError("Review could not be saved"))
    monkeypatch.setattr(reviews_router.svc, "submit_review", submit)

    response = client.post("/reviews", json={"activity_id": "activity-1", "text": "Useful."})

    assert response.status_code == 502
    assert response.json()["detail"] == "Review could not be saved"
