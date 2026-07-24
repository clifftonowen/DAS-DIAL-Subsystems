"""UNIT — /learners router in isolation.

TestClient exercises the HTTP layer (routing, auth dependency, serialization)
while the service method is monkeypatched, so only the router is under test.
`auth_ok` overrides `current_therapist` so no real token is needed.
"""
import pytest

from app.routers import learners as learners_router

pytestmark = pytest.mark.unit


def test_list_learners_returns_service_payload(client, auth_ok, monkeypatch):
    monkeypatch.setattr(learners_router.svc, "list_learners",
                        lambda: [{"id": "l1", "name": "Ada"}])

    resp = client.get("/learners")

    assert resp.status_code == 200
    assert resp.json() == [{"id": "l1", "name": "Ada"}]


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
