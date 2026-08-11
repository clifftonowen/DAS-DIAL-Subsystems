"""E2E use case: UC1 "Upload Assessment Data"

PM3's sequence, boundary to boundary over HTTP against the real test project — no mocking, a
real JWT, real rows:

    1-5   therapist picks a learner, a semester and a file, and uploads
    6     the system parses and stores the assessment data
    6.1   the file is invalid or corrupted            -> 400 / 422, nothing stored
    6.2   a mark is outside the rubric                -> 422, nothing stored
    7     a success message, and the data is ASSOCIATED WITH THE LEARNER

Step 7 is the one worth having. PM3 words it as "the uploaded assessment data is associated with
the selected learner", which is only observable through UC2: upload, then ask for the profile.
Before this branch that returned 409 "no assessment scores on record", because confirm wrote
`assessment_records` and ProfilingService reads `learner_sittings`.

These tests WRITE, so every case registers what it created with `cleanup_uploads`. A stray
sitting changes which semester is "latest" for a seeded learner and would break UC2's tests on
the next run.

Levels below this one need no setup: `pytest -m "unit or integration"`.
"""
import io
import os

import pytest

pytestmark = pytest.mark.e2e

# Written far enough ahead of the workbook's range (2022 Sem 1 - 2026 Sem 1) that these uploads
# are always the learner's newest sitting, and so never collide with seeded data.
E2E_SEMESTER = "2099 Sem 1"

REPORT_TEXT = """Assessment Date: 2026-07-24
Phoneme Segmentation 7 10
Confidence Score: 0.6
Risk Score: 0.4
Strengths: blending
Weaknesses: segmentation
"""


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def learner_id():
    value = os.environ.get("TEST_LEARNER_ID")
    if not value:
        pytest.skip("set TEST_LEARNER_ID to a learner in the test project (see infra/seed.sql)")
    return value


@pytest.fixture
def report_docx():
    """A real .docx built in memory — the repo ships no fixture binary."""
    docx = pytest.importorskip("docx")
    document = docx.Document()
    for line in REPORT_TEXT.splitlines():
        document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _payload(learner_id, **overrides):
    return {
        "learner_id": learner_id,
        "assessment_date": "2026-07-24",
        "risk_score": 0.4,
        "task_results": {"Phoneme Segmentation": {"score": 7, "max_score": 10}},
        "strengths": ["blending"],
        "weaknesses": ["segmentation"],
        "confidence_score": 0.6,
        "semester": E2E_SEMESTER,
        "band": "A2",
        "band_group": "A",
        "phonics_score": 30.0,
        "word_reading_score": 8.0,
        "word_spelling_score": 5.0,
        "writing_score": None,
        **overrides,
    }


# Steps 1-6 — parse a real report through the live API
def test_the_report_parses_into_a_preview_card(client, access_token, learner_id, report_docx):
    response = client.post(
        "/assessments/preview",
        data={"learner_id": learner_id},
        files={"file": ("report.docx", report_docx,
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        headers=_auth(access_token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["learner_id"] == learner_id
    assert body["risk_score"] == 0.4
    # The four marks are not in the report — the therapist types them in.
    assert body["phonics_score"] is None


# Step 7 — the postcondition, which is only visible through UC2
def test_generate_profile_returns_the_uploaded_marks(
    client, access_token, learner_id, cleanup_uploads
):
    cleanup_uploads(learner_id, E2E_SEMESTER)

    confirm = client.post(
        "/assessments/confirm", json=_payload(learner_id), headers=_auth(access_token),
    )
    assert confirm.status_code == 200

    profile = client.post(f"/profiles/{learner_id}", headers=_auth(access_token))

    assert profile.status_code == 200, "upload -> Generate Profile must not 409"
    body = profile.json()
    assert body["semester"] == E2E_SEMESTER
    assert body["phonics"] == 30.0
    assert body["source"] == "upload"
    # Plottable, not merely present: the radar needs a percentile as well as a mark.
    assert body["phonics_pct"] is not None
    # And the paper the learner never sat stays absent rather than becoming a zero.
    assert body["writing"] is None


def test_the_upload_appears_in_the_learners_history(
    client, access_token, learner_id, cleanup_uploads
):
    """The sitting joins the line chart's series, which is the other thing it is for."""
    cleanup_uploads(learner_id, E2E_SEMESTER)
    client.post("/assessments/confirm", json=_payload(learner_id), headers=_auth(access_token))

    sittings = client.get(f"/learners/{learner_id}/sittings", headers=_auth(access_token)).json()

    uploaded = [s for s in sittings if s["semester"] == E2E_SEMESTER]
    assert len(uploaded) == 1 and uploaded[0]["source"] == "upload"


def test_re_uploading_the_same_semester_replaces_rather_than_appends(
    client, access_token, learner_id, cleanup_uploads
):
    """The upsert key is (learner_id, semester): a corrected report overwrites.

    Also what makes confirm safe to retry after a partial failure — the reason the sitting is
    written before the record.
    """
    cleanup_uploads(learner_id, E2E_SEMESTER)
    client.post("/assessments/confirm",
                json=_payload(learner_id, phonics_score=30.0), headers=_auth(access_token))
    client.post("/assessments/confirm",
                json=_payload(learner_id, phonics_score=35.0), headers=_auth(access_token))

    sittings = client.get(f"/learners/{learner_id}/sittings", headers=_auth(access_token)).json()

    uploaded = [s for s in sittings if s["semester"] == E2E_SEMESTER]
    assert len(uploaded) == 1
    assert uploaded[0]["phonics"] == 35.0


# Step 6.1 — an invalid or corrupted file
@pytest.mark.parametrize("filename, content, expected", [
    ("notes.txt", b"not a report", 400),          # wrong extension: refused before parsing
    ("report.docx", b"not really a docx", 422),   # right extension, unreadable content
])
def test_an_unusable_file_is_rejected_and_stores_nothing(
    client, access_token, learner_id, filename, content, expected
):
    """400 and 422 stay distinct: the wrong file TYPE is fixed by picking another file, an
    unreadable REPORT is not."""
    response = client.post(
        "/assessments/preview",
        data={"learner_id": learner_id},
        files={"file": (filename, content, "application/octet-stream")},
        headers=_auth(access_token),
    )

    assert response.status_code == expected


# Step 6.2 — a mark outside the rubric
@pytest.mark.parametrize("field, value", [
    ("phonics_score", 51.0),        # ceiling is 50
    ("phonics_score", -1.0),
    ("writing_score", 31.0),        # ceiling is 30
    ("word_reading_score", 10.1),   # ceiling is 10
])
def test_a_mark_outside_the_rubric_is_refused(
    client, access_token, learner_id, field, value
):
    response = client.post(
        "/assessments/confirm",
        json=_payload(learner_id, **{field: value}),
        headers=_auth(access_token),
    )

    assert response.status_code == 422


def test_a_malformed_semester_is_refused(client, access_token, learner_id):
    """'2026 Sem 3' would store happily and sort wrong forever — the sitting would either never
    become the learner's latest or wrongly would, with nothing raising anywhere."""
    response = client.post(
        "/assessments/confirm",
        json=_payload(learner_id, semester="2026 Sem 3"),
        headers=_auth(access_token),
    )

    assert response.status_code == 422


def test_the_form_metadata_endpoints_answer(client, access_token):
    """The rubric and the semester list the upload form is built from.

    The ceilings served here are the ones the confirm validator enforces; if the two disagree
    the therapist meets a rejection the form said was fine.
    """
    metrics = client.get("/assessments/metrics", headers=_auth(access_token))
    semesters = client.get("/assessments/semesters", headers=_auth(access_token))

    assert metrics.status_code == 200 and semesters.status_code == 200
    assert {m["key"] for m in metrics.json()} == {
        "writing_score", "phonics_score", "word_reading_score", "word_spelling_score",
    }
    assert all(s.split(" Sem ")[1] in ("1", "2") for s in semesters.json())


def test_upload_requires_authentication(client, learner_id):
    """Assessment data is learner data; every endpoint here is behind the session."""
    assert client.get("/assessments/metrics").status_code in (401, 403)
    assert client.post("/assessments/confirm", json=_payload(learner_id)).status_code in (401, 403)
