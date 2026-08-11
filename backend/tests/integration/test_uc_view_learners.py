"""INTEGRATION — UC9 View Learner List, down to the DB driver.

Same filename as the e2e tier (`e2e/test_uc_view_learners.py`), per the convention that a use
case's tests carry its name in every tier directory. Bottom-up: real router, real service, real
repository; only the Supabase driver underneath is faked.

    IT-9.1  the assigned-vs-all toggle — both populations in one page
    IT-9.2  an empty caseload is a 200, not an error
    IT-9.3  a dead database surfaces as a 500 for the UI's retry
"""
import pytest

pytestmark = pytest.mark.integration

CASELOAD_ID = "11111111-1111-1111-1111-111111111111"
COHORT_ID = "22222222-2222-2222-2222-222222222222"


def caseload_row(learner_id=CASELOAD_ID, **overrides):
    """A therapist's learner who is also in the workbook: marks AND a name."""
    return {
        "id": learner_id, "student_id": "Student 0142", "pseudonym": "Aisha Binti Rahman",
        "tier": "Tier 2", "on_caseload": True,
        "semester": "2026 Sem 1", "band": "A2", "band_group": "A",
        "school_level": "Primary", "age": 9,
        "cluster_band": "A 3", "cluster_cohort": "Cohort 2",
        "phonics": 31.0, "word_reading_accuracy": 7.0, "word_spelling": 5.0, "writing": None,
        "fluency_mark": 14.0,
        "phonics_pct": 68.4, "word_reading_accuracy_pct": 41.0,
        "word_spelling_pct": 33.2, "writing_pct": None,
        **overrides,
    }


def cohort_row(learner_id=COHORT_ID, student_id="Student 0001", **overrides):
    """Anonymised research data: marks, no name, no caseload."""
    return caseload_row(
        learner_id, student_id=student_id, pseudonym="", tier="", on_caseload=False, **overrides
    )


def test_list_toggle_contract(client, auth_ok, fake_supabase):
    """IT-9.1: the toggle moves the therapist between their own learners and everyone.

    Default is the caseload alone; `caseload=false` widens to both populations in one page.
    This is the exact move UC9 exists for, end to end.
    """
    fake_supabase(seed={"learners": [
        caseload_row(),
        cohort_row(COHORT_ID, "Student 0001"),
    ]})

    mine = client.get("/learners").json()
    everyone = client.get("/learners?caseload=false").json()

    assert mine["total"] == 1
    assert mine["items"][0]["pseudonym"] == "Aisha Binti Rahman"
    assert everyone["total"] == 2
    assert {i["student_id"] for i in everyone["items"]} == {"Student 0142", "Student 0001"}


def test_list_empty_caseload_is_a_200(client, auth_ok, fake_supabase):
    """IT-9.2: a therapist with nobody assigned gets an empty page, not an error.

    The UI's empty state reads `total === 0` to decide what to say, so the empty case must
    arrive with the same payload shape as a populated one.
    """
    fake_supabase(seed={"learners": []})

    body = client.get("/learners").json()

    assert body["items"] == []
    assert body["total"] == 0


def test_list_db_failure_is_a_500(client, auth_ok, fake_supabase):
    """IT-9.3: a dead database surfaces as a 500 the UI can offer a retry for.

    The list path does not translate driver errors into a StorageError — they bubble up raw and
    FastAPI reports a generic 500. `fail_on_execute` puts the driver out of reach from the
    bottom of the call graph. TestClient re-raises by default, so assert the HTTP contract with
    a client that reports it.
    """
    from fastapi.testclient import TestClient

    from app.main import app

    fake_supabase(seed={"learners": [caseload_row()]},
                  fail_on_execute=ConnectionError("database unavailable"))

    resp = TestClient(app, raise_server_exceptions=False).get("/learners")

    assert resp.status_code == 500
