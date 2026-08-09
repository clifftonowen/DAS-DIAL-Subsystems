"""UNIT — /learners router in isolation.

TestClient exercises the HTTP layer (routing, auth dependency, serialization)
while the service method is monkeypatched, so only the router is under test.
`auth_ok` overrides `current_therapist` so no real token is needed.
"""
import pytest

from app.routers import learners as learners_router

pytestmark = pytest.mark.unit


def test_list_learners_returns_service_payload(client, auth_ok, monkeypatch):
    from app.schemas.dto import LearnerListItem, LearnerPage

    monkeypatch.setattr(
        learners_router.svc, "list_learners",
        lambda **_kw: LearnerPage(
            items=[LearnerListItem(id="l1", pseudonym="Ada", on_caseload=True)],
            total=1, page=1, per_page=24,
        ),
    )

    resp = client.get("/learners")

    assert resp.status_code == 200
    body = resp.json()
    assert body["items"][0]["pseudonym"] == "Ada"
    assert (body["total"], body["page"], body["per_page"]) == (1, 1, 24)


def test_list_learners_passes_the_query_string_through(client, auth_ok, monkeypatch):
    """The router owns parsing, the service owns clamping — this is the handover."""
    from app.schemas.dto import LearnerPage

    seen = {}

    def capture(**kwargs):
        seen.update(kwargs)
        return LearnerPage()

    monkeypatch.setattr(learners_router.svc, "list_learners", capture)

    client.get("/learners?page=3&per_page=50&q=aisha&caseload=false")

    assert seen == {"page": 3, "per_page": 50, "query": "aisha", "caseload_only": False}


def test_list_learners_rejects_an_absurd_page_size(client, auth_ok, monkeypatch):
    """Bounded at the router too, so a bad request is a 422 rather than a silent clamp."""
    monkeypatch.setattr(learners_router.svc, "list_learners", lambda **_kw: None)

    assert client.get("/learners?per_page=100000").status_code == 422


def test_list_learners_requires_auth(client):
    # No auth_ok override and no bearer token -> rejected by current_therapist.
    resp = client.get("/learners")
    assert resp.status_code in (401, 403)


def test_get_learner_propagates_404(client, auth_ok, monkeypatch):
    from fastapi import HTTPException

    def boom(_id):
        raise HTTPException(status_code=404, detail="Learner not found")

    monkeypatch.setattr(learners_router.svc, "get_learner", boom)

    resp = client.get("/learners/does-not-exist")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Learner not found"


# ── /learners/{id}/overview ───────────────────────────────────────────────────
def overview(**overrides):
    from app.schemas.dto import DialMetric, LearnerOverview

    return LearnerOverview(**{
        "learner_id": "l1", "pseudonym": "Ada", "band": "A2", "band_group": "A",
        "metrics": [DialMetric(key="phonics", label="Phonics", raw=31.0, max=46.0,
                               percentile=68.4, assessed=True)],
        **overrides,
    })


def test_overview_returns_service_payload(client, auth_ok, monkeypatch):
    monkeypatch.setattr(learners_router.overview_svc, "get_overview", lambda _id: overview())

    resp = client.get("/learners/l1/overview")

    assert resp.status_code == 200
    body = resp.json()
    assert body["pseudonym"] == "Ada"
    assert body["metrics"][0] == {
        "key": "phonics", "label": "Phonics", "raw": 31.0, "max": 46.0,
        "percentile": 68.4, "assessed": True,
    }


def test_overview_translates_a_missing_learner_to_404(client, auth_ok, monkeypatch):
    from app.services.learner_overview_service import LearnerNotFoundError

    def boom(_id):
        raise LearnerNotFoundError("No learner nope.")

    monkeypatch.setattr(learners_router.overview_svc, "get_overview", boom)

    resp = client.get("/learners/nope/overview")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "No learner nope."


def test_overview_with_no_scores_at_all_is_a_200(client, auth_ok, monkeypatch):
    """A learner with no marks and no history is an empty payload, not an error.

    The page has an empty state for each card and offers the upload flow; a 404 or a 500 here
    would hide a learner who simply has not been assessed yet.
    """
    monkeypatch.setattr(learners_router.overview_svc, "get_overview",
                        lambda _id: overview(metrics=[], history=[]))

    resp = client.get("/learners/l1/overview")

    assert resp.status_code == 200
    assert resp.json()["metrics"] == []
    assert resp.json()["history"] == []


def test_overview_requires_auth(client):
    assert client.get("/learners/l1/overview").status_code in (401, 403)
