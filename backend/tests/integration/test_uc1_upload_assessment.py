"""INTEGRATION — UC1 Upload Assessment Data. Bottom-up through the call graph.

Real AssessmentRepository, AssessmentService, AssessmentController introduced from the bottom
up; only the Supabase driver is faked. See the unit-level module docstring
(unit/test_uc1_upload_assessment.py) for why StorageError surfaces from the SERVICE
(AssessmentService.confirm_and_save) rather than the repository — AssessmentRepository.save()
is a bare upsert, mirroring ReviewRepository.save().

    IT-1.1 / 1.2   AssessmentRepository.save() + Supabase
    IT-1.3 / 1.4   AssessmentService (parse_preview + confirm_and_save) + repository + Supabase
    IT-1.5 / 1.6   AssessmentController (POST /assessments/preview, /confirm) + everything below

Uses real .docx bytes (python-docx) rather than PDF for the "parses correctly" cases: building a
byte-valid PDF that fitz will actually open is not worth the fragility here, and the parser's
.docx branch exercises exactly the same regex logic in assessment_parser.py.
"""
import io

import pytest
from fastapi import UploadFile

from app.ingestion.assessment_parser import ParseError
from app.schemas.dto import AssessmentConfirmRequest
from app.services.assessment_service import AssessmentService

pytestmark = pytest.mark.integration

LEARNER_ID = "11111111-1111-1111-1111-111111111111"

VALID_REPORT_LINES = [
    "DAS Literacy Assessment Report",
    "Assessment Date: 2026-07-24",
    "Task Results",
    "Task Score Max Score",
    "Phoneme Segmentation 7 10",
    "Nonword Decoding 4 10",
    "Summary",
    "Confidence Score: 0.6",
    "Risk Score: 0.4",
    "Strengths: Phoneme Segmentation",
    "Weaknesses: Nonword Decoding",
]


def _docx_bytes(lines):
    import docx
    document = docx.Document()
    for line in lines:
        document.add_paragraph(line)
    buf = io.BytesIO()
    document.save(buf)
    return buf.getvalue()


def confirm_request(**overrides):
    return AssessmentConfirmRequest(
        learner_id=LEARNER_ID, assessment_date="2026-07-24", risk_score=0.4,
        task_results={"Phoneme Segmentation": {"score": 7, "max_score": 10}},
        strengths=["Phoneme Segmentation"], weaknesses=["Nonword Decoding"],
        confidence_score=0.6, writing_score=0.0, phonics_score=0.0,
        word_reading_score=0.0, word_spelling_score=0.0,
        **overrides,
    )


# ── IT-1.1 / IT-1.2 — AssessmentRepository + Supabase ──────────────────────────
def test_it_1_1_save_persists_through_the_real_repository(fake_supabase):
    """IT-1.1: Supabase reachable — save() returns the saved record and it exists in the DB."""
    from app.repositories.assessment_repository import AssessmentRepository

    fake = fake_supabase(seed={"assessment_records": []})
    record = confirm_request().model_dump()
    record["learner_id"] = LEARNER_ID

    saved = AssessmentRepository().save(record)

    assert saved[0]["learner_id"] == LEARNER_ID
    assert len(fake.store["assessment_records"]) == 1


def test_it_1_2_save_does_not_persist_when_supabase_is_unreachable(fake_supabase):
    """IT-1.2: Supabase unreachable — the record is not saved (raw failure propagates)."""
    from app.repositories.assessment_repository import AssessmentRepository

    fake = fake_supabase(seed={"assessment_records": []},
                         fail_on_execute=ConnectionError("unreachable"))

    with pytest.raises(ConnectionError):
        AssessmentRepository().save({"learner_id": LEARNER_ID})

    assert fake.store["assessment_records"] == []


# ── IT-1.3 / IT-1.4 — AssessmentService + AssessmentRepository + Supabase ──────
def test_it_1_3_parse_and_confirm_round_trip_through_the_real_service(fake_supabase):
    """IT-1.3: valid learner id + file — parsed, then stored, and exists in the DB."""
    fake = fake_supabase(seed={"assessment_records": []})
    svc = AssessmentService()

    upload = UploadFile(file=io.BytesIO(_docx_bytes(VALID_REPORT_LINES)), filename="report.docx")
    parsed = svc.parse_preview(LEARNER_ID, upload)
    assert parsed.strengths == ["Phoneme Segmentation"]

    result = svc.confirm_and_save(AssessmentConfirmRequest(
        learner_id=parsed.learner_id, assessment_date=parsed.assessment_date,
        risk_score=parsed.risk_score, task_results=parsed.task_results,
        strengths=parsed.strengths, weaknesses=parsed.weaknesses,
        confidence_score=parsed.confidence_score,
        writing_score=0.0, phonics_score=0.0, word_reading_score=0.0, word_spelling_score=0.0,
    ))

    assert result["status"] == "success"
    assert len(fake.store["assessment_records"]) == 1
    assert fake.store["assessment_records"][0]["learner_id"] == LEARNER_ID


def test_it_1_4_a_parse_failure_never_reaches_storage(fake_supabase):
    """IT-1.4: a file with invalid/missing content — ParseError, nothing stored."""
    fake = fake_supabase(seed={"assessment_records": []})
    svc = AssessmentService()

    upload = UploadFile(file=io.BytesIO(_docx_bytes(["Just some unrelated prose."])),
                        filename="report.docx")

    with pytest.raises(ParseError):
        svc.parse_preview(LEARNER_ID, upload)

    assert fake.store["assessment_records"] == []


# ── IT-1.5 / IT-1.6 — AssessmentController + everything below ─────────────────
def test_it_1_5_preview_then_confirm_through_the_real_endpoints(client, auth_ok, fake_supabase):
    """IT-1.5: learner exists, Supabase reachable — the assessment is uploaded end to end."""
    fake = fake_supabase(seed={"assessment_records": []})

    preview_resp = client.post(
        "/assessments/preview",
        data={"learner_id": LEARNER_ID},
        files={"file": ("report.docx", _docx_bytes(VALID_REPORT_LINES),
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    assert preview_resp.status_code == 200
    body = preview_resp.json()

    confirm_resp = client.post("/assessments/confirm", json={
        "learner_id": body["learner_id"], "assessment_date": body["assessment_date"],
        "risk_score": body["risk_score"], "task_results": body["task_results"],
        "strengths": body["strengths"], "weaknesses": body["weaknesses"],
        "confidence_score": body["confidence_score"],
        "writing_score": 0.0, "phonics_score": 0.0,
        "word_reading_score": 0.0, "word_spelling_score": 0.0,
    })

    assert confirm_resp.status_code == 200
    assert len(fake.store["assessment_records"]) == 1


def test_it_1_6_preview_rejects_an_invalid_file_before_anything_is_stored(client, auth_ok, fake_supabase):
    """IT-1.6: an invalid file object — InvalidFormatError, nothing saved."""
    fake = fake_supabase(seed={"assessment_records": []})

    resp = client.post(
        "/assessments/preview",
        data={"learner_id": LEARNER_ID},
        files={"file": ("report.exe", b"MZ\x90\x00", "application/octet-stream")},
    )

    assert resp.status_code == 400
    assert fake.store["assessment_records"] == []
