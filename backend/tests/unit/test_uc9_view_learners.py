"""UNIT — UC9 View Learner List.

Same filename as the other tiers (`test_uc9_view_learners.py`), per the convention that a use
case's tests carry its name in every tier directory, so a plan ID traces straight to a file.

The plan's unit table:
    UT-9.1  LearnerRepository.list_page(caseload_only=True)  — returns the caseload
    UT-9.2  LearnerRepository.list_page(caseload_only=True)  — empty table, empty page
    UT-9.3  LearnerRepository.list_page()                    — dead database raises
    UT-9.4  LearnerService.list_learners()                   — populated page
    UT-9.5  LearnerService.list_learners()                   — empty page
    UT-9.6  LearnerController.list_learners()                — returns the payload
    UT-9.7  LearnerController.list_learners()                — handles a retrieval error (500)

The plan wrote UT-9.7 as "Service throws StorageError". The learner-list path deliberately has
no StorageError (the Reviews path is the one that translates); a driver failure surfaces raw
and FastAPI reports a generic 500 — which is what the UI's error state + Retry recover from.
"""
import pytest
from unittest.mock import Mock

pytestmark = pytest.mark.unit


# ── UT-9.1 / UT-9.2 / UT-9.3 — LearnerRepository.list_page ───────────────────
def caseload(learner_id, pseudonym, **overrides):
    return {"id": learner_id, "student_id": None, "pseudonym": pseudonym, "tier": "Tier 2",
            "on_caseload": True, "band": "A2", "band_group": "A", **overrides}


def cohort(learner_id, student_id, **overrides):
    return {"id": learner_id, "student_id": student_id, "pseudonym": "", "tier": "",
            "on_caseload": False, "band": "B4", "band_group": "B", **overrides}


def test_list_page_returns_the_caseload(fake_supabase):
    """UT-9.1: list_page(caseload_only=True) returns the therapist's own learners.

    The cohort shares the table, so the assertion is that it is EXCLUDED: a filter that
    ignored the flag would return both rows and this test would catch it.
    """
    from app.repositories.learner_repository import LearnerRepository

    fake_supabase(seed={"learners": [
        caseload("l1", "Aisha Binti Rahman"),
        cohort("c1", "Student 0001"),
    ]})

    rows, total = LearnerRepository().list_page(limit=24, offset=0, caseload_only=True)

    assert [r["id"] for r in rows] == ["l1"]
    assert total == 1


def test_list_page_returns_an_empty_page(fake_supabase):
    """UT-9.2: no learners at all is an empty page, not an error.

    The empty case must share the populated contract (rows + a filtered total), or the UI
    could not tell "no learners" apart from "could not load".
    """
    from app.repositories.learner_repository import LearnerRepository

    fake_supabase(seed={"learners": []})

    rows, total = LearnerRepository().list_page(limit=24, offset=0, caseload_only=True)

    assert rows == []
    assert total == 0


def test_list_page_surfaces_a_driver_failure(fake_supabase):
    """UT-9.3: a dead database raises out of list_page.

    There is no StorageError on this path — the driver exception bubbles up raw (UT-9.7 shows
    the router turning it into the 500 the UI recovers from).
    """
    from app.repositories.learner_repository import LearnerRepository

    fake_supabase(
        seed={"learners": [caseload("l1", "Aisha Binti Rahman")]},
        fail_on_execute=ConnectionError("database unavailable"),
    )

    with pytest.raises(ConnectionError):
        LearnerRepository().list_page(limit=24, offset=0, caseload_only=True)


# ── UT-9.4 / UT-9.5 — LearnerService.list_learners ───────────────────────────
def test_list_learners_returns_a_populated_page():
    """UT-9.4: a populated repository result becomes a populated page."""
    from app.services.learner_service import LearnerService

    svc = LearnerService()
    svc.learners = Mock()
    svc.learners.list_page.return_value = (
        [caseload("l1", "Aisha Binti Rahman")],
        137,
    )

    page = svc.list_learners(page=1, per_page=24)

    assert len(page.items) == 1
    assert page.items[0].pseudonym == "Aisha Binti Rahman"
    assert page.items[0].on_caseload is True
    assert page.total == 137, "the total is the filtered set, so the pager can size itself"


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


# ── UT-9.6 / UT-9.7 — LearnerController.list_learners ────────────────────────
def test_list_learners_returns_the_service_payload(client, auth_ok, monkeypatch):
    """UT-9.6: the controller resolves the session and hands back the service payload.

    `auth_ok` overrides `current_therapist`, standing in for a resolved session; the service
    is monkeypatched so only the HTTP layer is under test.
    """
    from app.routers import learners as learners_router
    from app.schemas.dto import LearnerListItem, LearnerPage

    monkeypatch.setattr(
        learners_router.svc, "list_learners",
        lambda **_kw: LearnerPage(
            items=[LearnerListItem(id="l1", pseudonym="Aisha Binti Rahman", on_caseload=True)],
            total=1, page=1, per_page=24,
        ),
    )

    resp = client.get("/learners")

    assert resp.status_code == 200
    body = resp.json()
    assert body["items"][0]["pseudonym"] == "Aisha Binti Rahman"
    assert (body["total"], body["page"], body["per_page"]) == (1, 1, 24)


def test_list_learners_surfaces_a_driver_failure(client, auth_ok, monkeypatch):
    """UT-9.7: a dead database is a 500, the UI's error state + Retry handle it.

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