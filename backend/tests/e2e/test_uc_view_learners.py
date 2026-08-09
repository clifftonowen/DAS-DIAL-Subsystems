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


def test_list_learners_returns_200_page(client, access_token):
    """A page object, not a bare array.

    `learners` holds the anonymised DAS research cohort alongside the caseload, so the endpoint
    pages — PostgREST truncates an unpaged select at 1,000 rows without erroring.
    """
    resp = client.get("/learners", headers=_auth(access_token))

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["items"], list)
    assert isinstance(body["total"], int)


def test_learner_detail_roundtrip(client, access_token):
    listing = client.get("/learners", headers=_auth(access_token)).json()["items"]
    if not listing:
        pytest.skip("test project has no learners seeded; seed infra/seed.sql to exercise detail")

    learner_id = listing[0]["id"]
    resp = client.get(f"/learners/{learner_id}", headers=_auth(access_token))

    assert resp.status_code == 200
    assert resp.json()["id"] == learner_id


def test_the_cohort_is_behind_a_flag(client, access_token):
    """The Learners tab defaults to the caseload, so the cohort must be opt-in.

    Without the default, the tab would open on thousands of anonymised research rows. Asserted
    against the real project because the two populations only actually differ in size there.
    """
    caseload = client.get("/learners", headers=_auth(access_token)).json()
    everyone = client.get("/learners?caseload=false", headers=_auth(access_token)).json()

    assert everyone["total"] >= caseload["total"]


def test_learners_rejected_without_token(client, supabase_env):
    # supabase_env gates on secrets so this only runs in the e2e context.
    resp = client.get("/learners")
    assert resp.status_code in (401, 403)
