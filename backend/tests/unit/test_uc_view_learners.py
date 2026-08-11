"""UNIT — UC9 View Learner List.

Same filename as the e2e tier (`e2e/test_uc_view_learners.py`), per the convention that a use
case's tests carry its name in every tier directory, so a plan ID traces straight to a file.

The plan's unit table:
    UT-9.5  LearnerService.list_learners() — returns an empty list
    UT-9.8  LearnerController.list_learners() — handles a retrieval error

The plan wrote UT-9.8 as "Service throws StorageError". The learner-list path deliberately has
no StorageError (the Reviews path is the one that translates); a driver failure surfaces raw
and FastAPI reports a generic 500 — which is what the UI's error state + Retry recover from.
"""
import pytest
from unittest.mock import Mock

pytestmark = pytest.mark.unit


def test_list_learners_returns_an_empty_page():
    """UT-9.5: an empty result is a 200 with an empty page, not an error.

    The UI reads `total` to decide between "no learners" and a populated grid, so the empty
    case must arrive with the same contract as the populated one.
    """
    from app.services.learner_service import LearnerService

    svc = LearnerService()
    svc.learners = Mock()
    svc.learners.list_page.return_value = ([], 0)

    page = svc.list_learners()

    assert page.items == []
    assert page.total == 0


def test_list_learners_surfaces_a_driver_failure(client, auth_ok, monkeypatch):
    """UT-9.8: a dead database is a 500, the UI's error state + Retry handle it.

    TestClient re-raises server exceptions by default, so assert the HTTP contract with a
    client that reports it.
    """
    from fastapi.testclient import TestClient

    from app.main import app
    from app.routers import learners as learners_router

    def boom(**kwargs):
        raise ConnectionError("database unavailable")

    monkeypatch.setattr(learners_router.svc, "list_learners", boom)

    resp = TestClient(app, raise_server_exceptions=False).get("/learners")

    assert resp.status_code == 500
