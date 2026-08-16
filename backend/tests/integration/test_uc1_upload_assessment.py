"""INTEGRATION — UC1 Upload Assessment Data. Call-graph, bottom-up.

Real AssessmentService, real repositories, real parser, real percentile computation; only the
Supabase driver is faked. Catches the wiring the unit tests cannot, because those mock the very
seams these exercise.

    Level 1   AssessmentRepository / LearnerSittingRepository  -> Supabase        IT-1.1, IT-1.2
    Level 2   AssessmentService  --parse-->     assessment_parser                 IT-1.3, IT-1.4
                                 --upsert-->    LearnerSittingRepository
                                 --save-->      AssessmentRepository
    Level 3   AssessmentController (POST /assessments/preview, /confirm)          IT-1.5, IT-1.6
    (above)   UC1 -> UC2: upload, then Generate Profile                           IT-1.7 - IT-1.9

IT-1.7 ONWARDS ARE NOT IN THE PM3 PLAN, and they are the reason this file matters. The plan's
UC1 postcondition is "the assessment data is associated with the selected learner", which was
untrue: `confirm_and_save` wrote only `assessment_records`, so a therapist could upload an
assessment and still be told the learner had no scores when they clicked Generate Profile. These
cases exercise the two use cases in sequence, which is the only way that gap is visible.
"""
import io

import pytest

pytestmark = pytest.mark.integration

LEARNER_ID = "11111111-1111-4111-8111-111111111111"
PEER_ID = "22222222-2222-4222-8222-222222222222"

REPORT_TEXT = """Assessment Date: 2026-07-24
Phoneme Segmentation 7 10
Confidence Score: 0.6
Risk Score: 0.4
Strengths: blending
Weaknesses: segmentation
"""


def docx_bytes(text: str = REPORT_TEXT) -> bytes:
    """A real .docx, generated rather than checked in — see the unit tier for why."""
    docx = pytest.importorskip("docx")
    document = docx.Document()
    for line in text.splitlines():
        document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _learner(**overrides):
    return {
        "id": LEARNER_ID, "pseudonym": "Aisha Binti Rahman", "tier": "Tier 2",
        "band": "A2", "band_group": "A", "on_caseload": True,
        **overrides,
    }


def _payload(**overrides):
    return {
        "learner_id": LEARNER_ID,
        "assessment_date": "2026-07-24",
        "risk_score": 0.4,
        "task_results": {"Phoneme Segmentation": {"score": 7, "max_score": 10}},
        "strengths": ["blending"],
        "weaknesses": ["segmentation"],
        "confidence_score": 0.6,
        "semester": "2026 Sem 1",
        "band": "A2",
        "band_group": "A",
        "phonics_score": 30.0,
        "word_reading_score": 8.0,
        "word_spelling_score": 5.0,
        "writing_score": None,
        **overrides,
    }


# --------------------------------------------------------------------------- #
# Level 1 — the repositories against the faked driver
# --------------------------------------------------------------------------- #
def test_it_1_1_the_record_repository_writes_through_to_the_database(fake_supabase):
    """IT-1.1: AssessmentRepository.save + Supabase — the row lands in the table."""
    from app.repositories.assessment_repository import AssessmentRepository

    fake = fake_supabase(seed={"assessment_records": []})

    AssessmentRepository().save({
        "id": "rec-1", "learner_id": LEARNER_ID, "assessment_date": "2026-07-24",
        "phonics_score": 30.0, "writing_score": None,
    })

    stored = fake.store["assessment_records"]
    assert len(stored) == 1 and stored[0]["phonics_score"] == 30.0


def test_it_1_2_a_database_failure_reaches_the_caller(fake_supabase):
    """IT-1.2: an unreachable driver raises rather than silently dropping the write."""
    from app.repositories.assessment_repository import AssessmentRepository

    fake_supabase(seed={"assessment_records": []},
                  fail_on_execute=RuntimeError("supabase unreachable"))

    with pytest.raises(Exception):
        AssessmentRepository().save({"id": "rec-1", "learner_id": LEARNER_ID})


# --------------------------------------------------------------------------- #
# Level 2 — AssessmentService over the real repositories
# --------------------------------------------------------------------------- #
def test_it_1_3_confirm_writes_both_tables(fake_supabase):
    """IT-1.3: one confirm, two rows — the sitting AND the assessment record.

    The sitting is the row the profile page and Generate Profile read; the record is the report
    as filed. Writing only the second is the gap this case exists to catch.
    """
    from app.services.assessment_service import AssessmentService
    from app.schemas.dto import AssessmentConfirmRequest

    fake = fake_supabase(seed={
        "learners": [_learner()], "learner_sittings": [], "assessment_records": [],
    })

    AssessmentService().confirm_and_save(AssessmentConfirmRequest(**_payload()))

    sitting = fake.store["learner_sittings"][0]
    assert sitting["learner_id"] == LEARNER_ID
    assert sitting["semester"] == "2026 Sem 1"
    assert sitting["source"] == "upload"
    assert sitting["phonics"] == 30.0
    assert sitting["writing"] is None                  # band A never sits it
    assert len(fake.store["assessment_records"]) == 1


def test_it_1_4_a_parse_failure_writes_nothing(fake_supabase):
    """IT-1.4: an unreadable report aborts before either table is touched.

    Driven through the REAL parser with a document that matches none of its patterns, rather
    than by monkeypatching the parser to raise.
    """
    from app.ingestion.assessment_parser import ParseError
    from app.services.assessment_service import AssessmentService

    fake = fake_supabase(seed={
        "learners": [_learner()], "learner_sittings": [], "assessment_records": [],
    })

    class _Upload:
        filename = "report.docx"
        file = io.BytesIO(docx_bytes("nothing useful here"))

    with pytest.raises(ParseError):
        AssessmentService().parse_preview(LEARNER_ID, _Upload())

    assert fake.store["learner_sittings"] == []
    assert fake.store["assessment_records"] == []


def test_it_1_4b_re_uploading_the_same_semester_replaces_the_sitting(fake_supabase):
    """IT-1.4: the upsert key is (learner_id, semester), so a correction overwrites.

    One sitting per learner per semester is the table's invariant. A second upload is normally a
    corrected report, so the newer marks win — and it makes `confirm` safe to retry after a
    partial failure, which is why the sitting is written first.
    """
    from app.services.assessment_service import AssessmentService
    from app.schemas.dto import AssessmentConfirmRequest

    fake = fake_supabase(seed={
        "learners": [_learner()], "learner_sittings": [], "assessment_records": [],
    })
    svc = AssessmentService()

    svc.confirm_and_save(AssessmentConfirmRequest(**_payload(phonics_score=30.0)))
    svc.confirm_and_save(AssessmentConfirmRequest(**_payload(phonics_score=35.0)))

    assert len(fake.store["learner_sittings"]) == 1
    assert fake.store["learner_sittings"][0]["phonics"] == 35.0


def test_it_1_4c_percentiles_are_ranked_against_the_same_semester_and_band(fake_supabase):
    """IT-1.4: the percentile is computed from rows actually in the table.

    The peer read, the ranking and the write are all real here — the unit tier stubs the peers,
    so this is what proves the query filters on (semester, band_group) rather than reading the
    whole table.
    """
    from app.services.assessment_service import AssessmentService
    from app.schemas.dto import AssessmentConfirmRequest

    fake = fake_supabase(seed={
        "learners": [_learner()],
        "learner_sittings": [
            # Same semester and band: these count.
            {"learner_id": PEER_ID, "semester": "2026 Sem 1", "band_group": "A", "phonics": 10.0},
            {"learner_id": "p2", "semester": "2026 Sem 1", "band_group": "A", "phonics": 20.0},
            # Different band, and a different semester: these must NOT.
            {"learner_id": "p3", "semester": "2026 Sem 1", "band_group": "B", "phonics": 46.0},
            {"learner_id": "p4", "semester": "2025 Sem 1", "band_group": "A", "phonics": 46.0},
        ],
        "assessment_records": [],
    })

    AssessmentService().confirm_and_save(AssessmentConfirmRequest(**_payload(phonics_score=30.0)))

    uploaded = next(s for s in fake.store["learner_sittings"] if s["learner_id"] == LEARNER_ID)
    # Population is [10, 20, 30] — the two in-scope peers plus this learner. Top of three.
    assert uploaded["phonics_pct"] == 100.0


# --------------------------------------------------------------------------- #
# Level 3 — the controller, through the HTTP boundary
# --------------------------------------------------------------------------- #
def test_it_1_5_post_confirm_stores_the_upload(client, auth_ok, fake_supabase):
    """IT-1.5: POST /assessments/confirm through router -> service -> repos -> fake."""
    fake = fake_supabase(seed={
        "learners": [_learner()], "learner_sittings": [], "assessment_records": [],
    })

    response = client.post("/assessments/confirm", json=_payload())

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert len(fake.store["learner_sittings"]) == 1


def test_it_1_6_post_preview_rejects_an_unsupported_file_with_400(client, auth_ok, fake_supabase):
    """IT-1.6: the wrong file type is refused at the boundary, and nothing is stored."""
    fake = fake_supabase(seed={
        "learners": [_learner()], "learner_sittings": [], "assessment_records": [],
    })

    response = client.post(
        "/assessments/preview",
        data={"learner_id": LEARNER_ID},
        files={"file": ("notes.txt", b"not a report", "text/plain")},
    )

    assert response.status_code == 400
    assert fake.store["assessment_records"] == []


def test_it_1_6b_an_out_of_range_mark_is_refused_before_anything_is_written(
    client, auth_ok, fake_supabase
):
    """IT-1.6: the boundary the validator enforces, exercised over HTTP.

    422 from pydantic, and — the half that matters — no partial write behind it.
    """
    fake = fake_supabase(seed={
        "learners": [_learner()], "learner_sittings": [], "assessment_records": [],
    })

    response = client.post("/assessments/confirm", json=_payload(phonics_score=51.0))

    assert response.status_code == 422
    assert fake.store["learner_sittings"] == []
    assert fake.store["assessment_records"] == []


def test_it_1_6c_a_malformed_semester_is_refused(client, auth_ok, fake_supabase):
    """IT-1.6: '2026 Sem 3' would store fine and sort wrong forever, so it is rejected here."""
    fake = fake_supabase(seed={
        "learners": [_learner()], "learner_sittings": [], "assessment_records": [],
    })

    response = client.post("/assessments/confirm", json=_payload(semester="2026 Sem 3"))

    assert response.status_code == 422
    assert fake.store["learner_sittings"] == []


# --------------------------------------------------------------------------- #
# UC1 -> UC2 — the postcondition PM3 claims, which was untrue before this branch
# --------------------------------------------------------------------------- #
def test_it_1_7_generate_profile_succeeds_after_an_upload(client, auth_ok, fake_supabase):
    """IT-1.7: upload, then Generate Profile. 200 with the uploaded marks — not 409.

    THE CASE THIS BRANCH EXISTS FOR. Before it, `confirm` wrote only `assessment_records`;
    ProfilingService reads `learner_sittings`, found nothing, and raised NoScoresError, which the
    router turns into 409 "no assessment scores on record". A therapist could upload an
    assessment and be told the learner had none.
    """
    fake = fake_supabase(seed={
        "learners": [_learner()], "learner_sittings": [], "assessment_records": [],
    })

    assert client.post("/assessments/confirm", json=_payload()).status_code == 200
    response = client.post(f"/profiles/{LEARNER_ID}")

    assert response.status_code == 200
    body = response.json()
    assert body["phonics"] == 30.0                 # the mark that was uploaded
    assert body["semester"] == "2026 Sem 1"
    assert body["source"] == "upload"              # promoted from the uploaded sitting
    # And it reached the learner row, which is what every other read uses.
    assert fake.store["learners"][0]["phonics"] == 30.0


def test_it_1_8_the_promoted_profile_carries_percentiles(client, auth_ok, fake_supabase):
    """IT-1.8: the promoted marks are PLOTTABLE, not just present.

    LearnerOverviewService counts a metric as assessed only when it has both a mark and a
    percentile. A 200 from Generate Profile with null percentiles would still render every radar
    axis as "not assessed" — the upload would look successful and show the therapist nothing.
    """
    fake_supabase(seed={
        "learners": [_learner()],
        "learner_sittings": [
            {"learner_id": PEER_ID, "semester": "2026 Sem 1", "band_group": "A", "phonics": 10.0},
        ],
        "assessment_records": [],
    })

    client.post("/assessments/confirm", json=_payload())
    body = client.post(f"/profiles/{LEARNER_ID}").json()

    assert body["phonics_pct"] is not None
    assert body["writing_pct"] is None             # no mark, so no percentile — correctly null


def test_it_1_9_an_unassessed_paper_survives_promotion_as_null(client, auth_ok, fake_supabase):
    """IT-1.9: writing stays null end to end, rather than becoming a mark of zero.

    A 0 here would rank as the learner's weakest skill and steer UC3 into generating a writing
    activity for a band-A learner who has never sat the paper.
    """
    fake = fake_supabase(seed={
        "learners": [_learner()], "learner_sittings": [], "assessment_records": [],
    })

    client.post("/assessments/confirm", json=_payload(writing_score=None))
    client.post(f"/profiles/{LEARNER_ID}")

    assert fake.store["learners"][0]["writing"] is None
