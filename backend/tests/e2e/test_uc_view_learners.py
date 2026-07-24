"""E2E use case: "Therapist views their learners".

Full stack against the REAL Supabase test project (no fakes): TestClient runs
the real app, `current_therapist` verifies a REAL JWT, and repositories hit the
real database. Auto-skips when the test-project secrets / test-user env are
absent (see conftest: supabase_env, access_token), so local runs without
secrets stay green.
"""
import pytest

pytestmark = pytest.mark.e2e


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_list_learners_returns_200_list(client, access_token):
    resp = client.get("/learners", headers=_auth(access_token))

    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_learner_detail_roundtrip(client, access_token):
    listing = client.get("/learners", headers=_auth(access_token)).json()
    if not listing:
        pytest.skip("test project has no learners seeded; seed infra/seed.sql to exercise detail")

    learner_id = listing[0]["id"]
    resp = client.get(f"/learners/{learner_id}", headers=_auth(access_token))

    assert resp.status_code == 200
    assert resp.json()["id"] == learner_id


def test_learners_rejected_without_token(client, supabase_env):
    # supabase_env gates on secrets so this only runs in the e2e context.
    resp = client.get("/learners")
    assert resp.status_code in (401, 403)
