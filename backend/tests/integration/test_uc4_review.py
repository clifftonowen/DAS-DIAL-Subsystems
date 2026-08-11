"""INTEGRATION — UC4 Submit Review, bottom-up through the call graph.

Real ReviewRepository, ReviewService and ReviewController are introduced from
the bottom upwards. Authentication and the Supabase driver remain test seams.
The frontend-to-controller edge is covered by the MSW integration test in
frontend/src/views/__integration__/UC4Review.integration.test.jsx.
"""
import pytest

from app.services.review_service import ReviewService, StorageError

pytestmark = pytest.mark.integration


class _UnavailableTable:
    def upsert(self, _payload):
        return self

    def execute(self):
        raise ConnectionError("database unavailable")


class _UnavailableSupabase:
    def table(self, _name):
        return _UnavailableTable()


def make_database_unavailable(monkeypatch):
    """Fail only at the external database-driver seam."""
    import app.repositories.base as base

    monkeypatch.setattr(base, "get_supabase", lambda: _UnavailableSupabase())


def test_it_4_1_service_and_repository_store_a_valid_review(fake_supabase):
    fake = fake_supabase(seed={"reviews": []})

    result = ReviewService().submit_review(
        "activity-1", "therapist-1", "Useful activity.", None,
    )

    assert result == {
        "activity_id": "activity-1",
        "therapist_id": "therapist-1",
        "text": "Useful activity.",
        "approval_status": None,
        "reviewer": {"id": "therapist-1"},
    }
    assert fake.store["reviews"] == [{
        "activity_id": "activity-1",
        "therapist_id": "therapist-1",
        "text": "Useful activity.",
        "approval_status": None,
    }]


def test_it_4_2_service_and_repository_report_a_storage_failure(monkeypatch):
    make_database_unavailable(monkeypatch)

    with pytest.raises(StorageError, match="Review could not be saved"):
        ReviewService().submit_review(
            "activity-1", "therapist-1", "Useful activity.", None,
        )


def test_it_4_3_controller_saves_through_real_service_and_repository(
    client, auth_ok, fake_supabase,
):
    fake = fake_supabase(seed={"reviews": []})

    response = client.post("/reviews", json={
        "activity_id": "activity-1", "text": "Useful activity.",
    })

    assert response.status_code == 200
    assert response.json()["text"] == "Useful activity."
    assert fake.store["reviews"] == [{
        "activity_id": "activity-1",
        "therapist_id": auth_ok,
        "text": "Useful activity.",
        "approval_status": None,
    }]


def test_blank_text_regression_stops_before_the_repository(
    client, auth_ok, fake_supabase,
):
    fake = fake_supabase(seed={"reviews": []})

    response = client.post("/reviews", json={
        "activity_id": "activity-1", "text": "   ",
    })

    assert response.status_code == 422
    assert fake.queries_on("reviews") == []
    assert fake.store["reviews"] == []


def test_it_4_5_invalid_session_stops_before_the_repository(client, fake_supabase):
    fake = fake_supabase(seed={"reviews": []})

    response = client.post("/reviews", json={
        "activity_id": "activity-1", "text": "Useful activity.",
    })

    assert response.status_code == 401
    assert fake.queries_on("reviews") == []


def test_it_4_4_storage_failure_reaches_the_controller_response(
    client, auth_ok, monkeypatch,
):
    make_database_unavailable(monkeypatch)

    response = client.post("/reviews", json={
        "activity_id": "activity-1", "text": "Useful activity.",
    })

    assert response.status_code == 502
    assert response.json()["detail"] == "Review could not be saved"


@pytest.mark.parametrize("decision", ["APPROVED", "REJECTED"])
def test_uc4_decision_is_stored_without_overwriting_uc3_status(
    decision, client, auth_ok, fake_supabase,
):
    """Expanded UC4 remains independent of UC3 automated validation."""
    fake = fake_supabase(seed={
        "reviews": [],
        "learning_activities": [{"id": "activity-1", "status": "GENERATED"}],
    })

    response = client.post("/reviews", json={
        "activity_id": "activity-1", "text": "Useful activity.",
        "approval_status": decision,
    })

    assert response.status_code == 200
    assert response.json()["approval_status"] == decision
    assert fake.store["reviews"][0]["approval_status"] == decision
    assert fake.store["learning_activities"][0]["status"] == "GENERATED"
    assert fake.queries_on("learning_activities") == []
