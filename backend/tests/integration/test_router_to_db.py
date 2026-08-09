"""INTEGRATION level 3 (top) — full call graph minus the DB driver.

TestClient -> router -> real service -> real repository -> FakeSupabase.
Every layer is the production object; only the Supabase network client is
substituted and `current_therapist` is overridden. This is the widest slice
that still runs hermetically (no secrets, no real project).
"""
import pytest

pytestmark = pytest.mark.integration


def test_list_learners_end_to_end_through_fake_db(client, auth_ok, fake_supabase):
    fake_supabase(seed={"learners": [
        {"id": "l1", "pseudonym": "Ada", "on_caseload": True},
        {"id": "l2", "pseudonym": "Bo", "on_caseload": True},
    ]})

    resp = client.get("/learners")

    assert resp.status_code == 200
    # A page object, not a bare array — see LearnerPage for why the shape changed.
    body = resp.json()
    assert {r["pseudonym"] for r in body["items"]} == {"Ada", "Bo"}
    assert body["total"] == 2


def test_get_learner_detail_end_to_end(client, auth_ok, fake_supabase):
    fake_supabase(seed={"learners": [{"id": "l1", "pseudonym": "Ada", "on_caseload": True}]})

    resp = client.get("/learners/l1")

    assert resp.status_code == 200
    assert resp.json()["pseudonym"] == "Ada"


def test_get_missing_learner_returns_404_end_to_end(client, auth_ok, fake_supabase):
    fake_supabase(seed={"learners": []})

    resp = client.get("/learners/nope")

    assert resp.status_code == 404
