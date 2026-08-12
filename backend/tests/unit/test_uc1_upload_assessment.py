"""UNIT — UC1 Upload Assessment Data.

The PM3 plan describes one controller method, `uploadAssessment()`, that parses AND stores in a
single call. The shipped code splits that into two phases — POST /assessments/preview (parse
only, nothing is saved) and POST /assessments/confirm (store, once the therapist has reviewed
the card) — because the UI shows a preview card before committing. Each plan row is mapped onto
whichever phase actually does that step:

    AB1.2   AssessmentController.preview_assessment   UT-1.1, UT-1.2
    AB1.2b  AssessmentController.confirm_assessment    (extends the plan — the store phase)
    AB1.3   AssessmentService.parse_preview            UT-1.3, UT-1.4
    AB1.3b  AssessmentService.confirm_and_save          (extends the plan — the store phase)
    AB1.4   AssessmentRepository.save                   UT-1.5, UT-1.6

UT-1.6 in the plan reads "AssessmentRepository.save() returns StorageError". The repository
itself does not catch anything — `save()` is a bare upsert, exactly like ReviewRepository.save()
— so a driver failure propagates as the raw exception; AssessmentService.confirm_and_save is
what turns it into StorageError, mirroring ReviewService (see test_review_service.py). Both
halves are pinned here: the repository case proves the failure is not swallowed, the service
case proves the translation.
"""
import io
from unittest.mock import Mock

import pytest
from fastapi import UploadFile

from app.ingestion.assessment_parser import InvalidFormatError, ParseError
from app.schemas.dto import AssessmentConfirmRequest, AssessmentPreview
from app.services.assessment_service import AssessmentService, StorageError

pytestmark = pytest.mark.unit

LEARNER_ID = "11111111-1111-1111-1111-111111111111"


def upload_file(filename="report.pdf", content=b"%PDF-1.4 fake pdf bytes"):
    return UploadFile(file=io.BytesIO(content), filename=filename)


def preview(**overrides):
    return AssessmentPreview(
        learner_id=LEARNER_ID, assessment_date="2026-07-24",
        tasks=[], strengths=["Phoneme Segmentation"], weaknesses=["Nonword Decoding"],
        confidence_score=0.6, risk_score=0.4, task_results={}, notes="",
        writing_score=12.0, phonics_score=30.0, word_reading_score=6.0, word_spelling_score=7.0,
        **overrides,
    )


def confirm_request(**overrides):
    return AssessmentConfirmRequest(
        learner_id=LEARNER_ID, assessment_date="2026-07-24", risk_score=0.4,
        task_results={}, strengths=[], weaknesses=[], confidence_score=0.6,
        writing_score=12.0, phonics_score=30.0, word_reading_score=6.0, word_spelling_score=7.0,
        **overrides,
    )


# ── AB1.2 — AssessmentController.preview_assessment (the parse phase) ─────────
def test_ut_1_1_preview_returns_the_parsed_preview_on_a_valid_file(client, auth_ok, monkeypatch):
    """UT-1.1: a valid learner id and file object — no error, the assessment is parsed."""
    from app.routers import assessments as assessments_router

    monkeypatch.setattr(assessments_router.svc, "parse_preview", lambda _lid, _f: preview())

    resp = client.post(
        "/assessments/preview",
        data={"learner_id": LEARNER_ID},
        files={"file": ("report.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )

    assert resp.status_code == 200
    assert resp.json()["learner_id"] == LEARNER_ID
    assert resp.json()["strengths"] == ["Phoneme Segmentation"]


def test_ut_1_2_preview_returns_400_on_an_invalid_file(client, auth_ok, monkeypatch):
    """UT-1.2: an invalid file object — InvalidFormatError, nothing is stored."""
    from app.routers import assessments as assessments_router

    def boom(_lid, _f):
        raise InvalidFormatError("Unsupported file type 'report.txt'.")

    monkeypatch.setattr(assessments_router.svc, "parse_preview", boom)

    resp = client.post(
        "/assessments/preview",
        data={"learner_id": LEARNER_ID},
        files={"file": ("report.txt", b"not a report", "text/plain")},
    )

    assert resp.status_code == 400
    assert "Unsupported file type" in resp.json()["detail"]


def test_preview_requires_authentication(client):
    resp = client.post(
        "/assessments/preview",
        data={"learner_id": LEARNER_ID},
        files={"file": ("report.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert resp.status_code in (401, 403)


# ── AB1.2b — AssessmentController.confirm_assessment (the store phase) ────────
def test_confirm_stores_a_valid_preview(client, auth_ok, monkeypatch):
    from app.routers import assessments as assessments_router

    monkeypatch.setattr(
        assessments_router.svc, "confirm_and_save",
        lambda _payload: {"status": "success", "message": "Data saved successfully", "record": {}},
    )

    resp = client.post("/assessments/confirm", json=confirm_request().model_dump())

    assert resp.status_code == 200
    assert resp.json()["status"] == "success"


def test_confirm_returns_500_on_a_storage_failure(client, auth_ok, monkeypatch):
    """UT-1.6 (controller half): a StorageError from the service surfaces as a 500."""
    from app.routers import assessments as assessments_router

    def boom(_payload):
        raise StorageError("connection refused")

    monkeypatch.setattr(assessments_router.svc, "confirm_and_save", boom)

    resp = client.post("/assessments/confirm", json=confirm_request().model_dump())

    assert resp.status_code == 500
    assert "connection refused" in resp.json()["detail"]


def test_confirm_requires_authentication(client):
    resp = client.post("/assessments/confirm", json=confirm_request().model_dump())
    assert resp.status_code in (401, 403)


# ── AB1.3 — AssessmentService.parse_preview ────────────────────────────────────
def test_ut_1_3_parse_preview_returns_the_parsed_report(monkeypatch):
    """UT-1.3: a valid file object is parsed and returned, ok."""
    import app.services.assessment_service as svc_module

    monkeypatch.setattr(svc_module, "validate_format", lambda _f: None)
    monkeypatch.setattr(svc_module, "parse_assessment_report", lambda _f, _lid: preview())

    out = AssessmentService().parse_preview(LEARNER_ID, upload_file())

    assert out.learner_id == LEARNER_ID


def test_ut_1_4_parse_preview_raises_parse_error_on_bad_content(monkeypatch):
    """UT-1.4: a valid file object with invalid/missing content raises ParseError."""
    import app.services.assessment_service as svc_module

    monkeypatch.setattr(svc_module, "validate_format", lambda _f: None)

    def boom(_f, _lid):
        raise ParseError("No extractable text found in the document.")

    monkeypatch.setattr(svc_module, "parse_assessment_report", boom)

    with pytest.raises(ParseError):
        AssessmentService().parse_preview(LEARNER_ID, upload_file())


def test_parse_preview_rejects_before_ever_parsing_an_invalid_format(monkeypatch):
    """AB1.3 extension: validate_format runs first, so a bad extension never reaches the parser."""
    import app.services.assessment_service as svc_module

    def reject(_f):
        raise InvalidFormatError("Unsupported file type 'report.txt'.")

    monkeypatch.setattr(svc_module, "validate_format", reject)
    parse_calls = []
    monkeypatch.setattr(
        svc_module, "parse_assessment_report",
        lambda *a, **k: parse_calls.append(1) or preview(),
    )

    with pytest.raises(InvalidFormatError):
        AssessmentService().parse_preview(LEARNER_ID, upload_file(filename="report.txt"))

    assert parse_calls == [], "the parser must never run once the format is rejected"


# ── AB1.3b — AssessmentService.confirm_and_save (extends the plan) ────────────
def test_confirm_and_save_calls_the_repository_with_a_json_safe_record():
    svc = AssessmentService()
    svc.assessments = Mock()
    svc.assessments.save.return_value = {"id": "row-1"}

    out = svc.confirm_and_save(confirm_request())

    assert out["status"] == "success"
    saved = svc.assessments.save.call_args.args[0]
    assert saved["learner_id"] == LEARNER_ID
    assert isinstance(saved["assessment_date"], str)   # JSON-safe, not a date object


def test_confirm_and_save_translates_a_repository_failure_into_storage_error():
    """UT-1.6 (service half): the repository's raw failure becomes StorageError here, not there."""
    svc = AssessmentService()
    svc.assessments = Mock()
    svc.assessments.save.side_effect = ConnectionError("connection refused")

    with pytest.raises(StorageError, match="connection refused"):
        svc.confirm_and_save(confirm_request())


# ── AB1.4 — AssessmentRepository.save ──────────────────────────────────────────
def test_ut_1_5_save_stores_and_returns_the_record(fake_supabase):
    """UT-1.5: a reachable Supabase client stores a valid AssessmentRecord."""
    from app.repositories.assessment_repository import AssessmentRepository

    fake = fake_supabase(seed={"assessment_records": []})
    record = confirm_request().model_dump()
    record["learner_id"] = LEARNER_ID

    saved = AssessmentRepository().save(record)

    assert saved[0]["learner_id"] == LEARNER_ID
    assert fake.store["assessment_records"] == [record]


def test_ut_1_6_save_propagates_a_database_failure(fake_supabase):
    """UT-1.6: an unreachable Supabase client — the repository does not swallow the failure.

    Mirrors ReviewRepository.save(): AssessmentRepository.save() is a bare upsert with no
    try/except, so the caller (AssessmentService.confirm_and_save) is what turns this into a
    StorageError — see test_confirm_and_save_translates_a_repository_failure_into_storage_error.
    """
    from app.repositories.assessment_repository import AssessmentRepository

    fake_supabase(seed={"assessment_records": []},
                  fail_on_execute=ConnectionError("database unavailable"))

    with pytest.raises(ConnectionError, match="database unavailable"):
        AssessmentRepository().save({"learner_id": LEARNER_ID})
