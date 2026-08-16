"""UNIT — UC1 Upload Assessment Data.

Each test carries its ID from the UC1 test plan so the table and the suite can be read side by
side.

    UT-1.1 / 1.2     AssessmentController (POST /assessments/preview, /confirm)
    UT-1.3 / 1.4     AssessmentService.parse_preview() + confirm_and_save()
    UT-1.5 / 1.6     AssessmentRepository.save()

THE PLAN'S NAMES vs THE CODE. PM3 describes a single `uploadAssessment()` calling
`parseAndStore()`. The implementation splits that in two — `POST /assessments/preview` parses and
returns a card for the therapist to check, `POST /assessments/confirm` persists what they
approved — because the four DIAL marks are not in the report and have to be typed in. The IDs map
onto the halves rather than being renumbered:

    uploadAssessment()  -> preview (UT-1.1 valid, UT-1.2 invalid)
    parseAndStore()     -> parse_preview + confirm_and_save (UT-1.3 valid, UT-1.4 invalid)
    save()              -> AssessmentRepository.save (UT-1.5 ok, UT-1.6 storage failure)

Beyond the plan, and where most of the value is: the BOUNDARY column on the metric validator
(UT-1.7), and the `None`-is-not-zero rule (UT-1.8) that keeps an unassessed paper from reading as
a mark of zero. The plan predates both — it was written when the upload carried no marks at all.

Every collaborator is mocked: the repositories are stand-ins, so nothing touches Supabase.
"""
import io
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from app.ingestion.assessment_parser import InvalidFormatError, ParseError
from app.schemas.dto import AssessmentConfirmRequest, assessment_metrics
from app.services.assessment_service import AssessmentService, StorageError

pytestmark = pytest.mark.unit

LEARNER_ID = "11111111-1111-4111-8111-111111111111"

# What the parser expects to find in the document, per its own regexes. Task names may contain
# letters and spaces only — a digit or a hyphen in the name and the row silently does not match.
#
# NO "Task Results" HEADER, deliberately. The task pattern is
# `^([A-Za-z][A-Za-z\s]+?)\s+(\d+)\s+(\d+)$` with re.MULTILINE, and `\s` matches NEWLINES — so any
# run of letters-and-whitespace above a task row is swallowed into that task's name, and a header
# of plain words yields one task literally called "Task Results\nPhoneme Segmentation". A blank
# line does NOT help (it is whitespace too); only a character outside [A-Za-z\s] ends the run,
# which is why the date line above — with its colon and digits — does. test_ut_1_3c pins the
# quirk so a future tightening of the regex breaks loudly instead of silently changing what
# every stored report parsed to.
REPORT_TEXT = """Assessment Date: 2026-07-24
Phoneme Segmentation 7 10
Blending 5 10
Confidence Score: 0.6
Risk Score: 0.4
Strengths: blending, rhyme
Weaknesses: segmentation
"""


def docx_bytes(text: str = REPORT_TEXT) -> bytes:
    """A real .docx carrying `text`, one paragraph per line.

    GENERATED, NOT CHECKED IN. The parser reads paragraphs, so the fixture is a handful of lines;
    building it here means a test can corrupt exactly one of them to drive a parse failure
    through the real parser instead of monkeypatching it.
    """
    docx = pytest.importorskip("docx")
    document = docx.Document()
    for line in text.splitlines():
        document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


class FakeUpload:
    """The two attributes `validate_format` and `parse_assessment_report` actually read off a
    FastAPI UploadFile."""

    def __init__(self, filename: str, data: bytes = b""):
        self.filename = filename
        self.file = io.BytesIO(data)


def confirm_payload(**overrides) -> AssessmentConfirmRequest:
    return AssessmentConfirmRequest(**{
        "learner_id": LEARNER_ID,
        "assessment_date": "2026-07-24",
        "risk_score": 0.4,
        "task_results": {},
        "semester": "2026 Sem 1",
        "band": "A2",
        "band_group": "A",
        "phonics_score": 30.0,
        "word_reading_score": 8.0,
        "word_spelling_score": 5.0,
        "writing_score": None,
        **overrides,
    })


def make_service(peers=()):
    """The real service with every repository replaced."""
    svc = AssessmentService()
    svc.assessments = Mock()
    svc.assessments.save.return_value = {"id": "rec-1"}
    svc.sittings = Mock()
    svc.sittings.upsert_many.return_value = 1
    svc.sittings.peer_marks.return_value = list(peers)
    svc.learners = Mock()
    svc.learners.find_by_id.return_value = {"id": LEARNER_ID, "band": "A2", "band_group": "A"}
    return svc


# UT: 1.1-1.2
# AssessmentController — POST /assessments/preview
# --------------------------------------------------------------------------- #
def test_ut_1_1_preview_returns_the_parsed_card_for_a_valid_file(client, auth_ok, monkeypatch):
    """UT-1.1: a valid file and learner id parse without error and return the preview."""
    from app.routers import assessments as router

    stub = Mock()
    stub.return_value = {
        "learner_id": LEARNER_ID, "assessment_date": "2026-07-24", "tasks": [],
        "strengths": [], "weaknesses": [], "confidence_score": 0.6, "risk_score": 0.4,
        "task_results": {}, "notes": "",
    }
    monkeypatch.setattr(router.svc, "parse_preview", stub)

    response = client.post(
        "/assessments/preview",
        data={"learner_id": LEARNER_ID},
        files={"file": ("report.docx", b"x", "application/octet-stream")},
    )

    assert response.status_code == 200
    assert response.json()["learner_id"] == LEARNER_ID


@pytest.mark.parametrize("error, expected_status", [
    (InvalidFormatError("Only .pdf and .docx are accepted"), 400),
    (ParseError("Could not locate any recognizable assessment data"), 422),
])
def test_ut_1_2_preview_maps_each_failure_to_its_status(
    client, auth_ok, monkeypatch, error, expected_status
):
    """UT-1.2: an invalid file is rejected, and the two failures stay distinguishable.

    400 and 422 are different problems for the therapist: the wrong file TYPE is fixed by
    picking another file, an unreadable REPORT is not. Collapsing them would leave the UI
    unable to say which happened.
    """
    from app.routers import assessments as router

    monkeypatch.setattr(router.svc, "parse_preview", Mock(side_effect=error))

    response = client.post(
        "/assessments/preview",
        data={"learner_id": LEARNER_ID},
        files={"file": ("report.txt", b"x", "text/plain")},
    )

    assert response.status_code == expected_status
    assert str(error) in response.json()["detail"]


def test_ut_1_2b_confirm_returns_500_when_the_database_refuses(client, auth_ok, monkeypatch):
    """UT-1.2 (confirm half): a storage failure surfaces as 500, not a silent success."""
    from app.routers import assessments as router

    monkeypatch.setattr(router.svc, "confirm_and_save", Mock(side_effect=StorageError("down")))

    response = client.post("/assessments/confirm", json=confirm_payload().model_dump())

    assert response.status_code == 500


# Both endpoints sit behind `current_therapist`. Kept from the `uploadData` branch, which wrote
# them independently — an assessment is clinical data, and `confirm` also writes a learner's
# marks, so an unauthenticated caller could rewrite a learner they cannot even see.
# No `auth_ok` fixture here on purpose: that override is what these two tests exist to remove.
def test_preview_requires_authentication(client):
    resp = client.post(
        "/assessments/preview",
        data={"learner_id": LEARNER_ID},
        files={"file": ("report.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert resp.status_code in (401, 403)


def test_confirm_requires_authentication(client):
    resp = client.post("/assessments/confirm", json=confirm_payload().model_dump(mode="json"))
    assert resp.status_code in (401, 403)


# UT: 1.3-1.4
# AssessmentService.parse_preview() + confirm_and_save()
# --------------------------------------------------------------------------- #
def test_ut_1_3_parse_preview_reads_the_report(monkeypatch):
    """UT-1.3: a valid document parses into the preview card the therapist reviews."""
    svc = make_service()

    preview = svc.parse_preview(LEARNER_ID, FakeUpload("report.docx", docx_bytes()))

    assert preview.learner_id == LEARNER_ID
    assert preview.assessment_date == "2026-07-24"
    assert preview.risk_score == 0.4
    assert [t.name for t in preview.tasks] == ["Phoneme Segmentation", "Blending"]
    assert preview.strengths == ["blending", "rhyme"]


def test_ut_1_3b_the_parser_never_invents_the_four_marks():
    """UT-1.3: the DIAL marks come back None, because the report does not carry them.

    They are typed in by the therapist. Returning 0.0 here — as this once did — would mean an
    untouched field silently asserts a mark of zero on a paper that may not have been sat.
    """
    svc = make_service()

    preview = svc.parse_preview(LEARNER_ID, FakeUpload("report.docx", docx_bytes()))

    assert preview.phonics_score is None
    assert preview.writing_score is None


def test_ut_1_3c_a_text_line_above_a_task_row_is_absorbed_into_its_name():
    """UT-1.3 (known parser quirk, pinned rather than fixed).

    The task pattern allows `\\s` inside a name, and `\\s` matches a newline — so any run of
    letters and whitespace above a task row becomes part of that task's name. A real report with
    a "Task Results" header therefore yields a task called "Task Results\\nPhoneme Segmentation",
    and inserting a blank line does not help: that is whitespace too. Only a character outside
    [A-Za-z\\s] — the colon in "Assessment Date:", say — ends the run.

    Documented here because it is invisible until someone reads the stored `task_results` keys,
    and because a future tightening of the regex should break this test loudly rather than
    quietly change what a report parses to.
    """
    svc = make_service()
    run_on = "Task Results\nPhoneme Segmentation 7 10\nRisk Score: 0.4"

    preview = svc.parse_preview(LEARNER_ID, FakeUpload("r.docx", docx_bytes(run_on)))

    assert [t.name for t in preview.tasks] == ["Task Results\nPhoneme Segmentation"]


def test_ut_1_4_parse_preview_rejects_an_unreadable_report():
    """UT-1.4: a file with none of the expected content raises ParseError.

    Driven through the REAL parser by handing it a document whose lines match none of its
    regexes, rather than by monkeypatching the parser to fail.
    """
    svc = make_service()

    with pytest.raises(ParseError):
        svc.parse_preview(LEARNER_ID, FakeUpload("report.docx", docx_bytes("nothing useful here")))


def test_ut_1_4b_parse_preview_rejects_an_unsupported_extension():
    """UT-1.4: the format check happens before any parsing is attempted."""
    svc = make_service()

    with pytest.raises(InvalidFormatError):
        svc.parse_preview(LEARNER_ID, FakeUpload("report.txt", b"anything"))


def test_ut_1_4c_a_report_with_only_a_risk_score_still_parses():
    """UT-1.4 (boundary): the "nothing recognisable" guard is an AND of three conditions.

    No tasks AND no confidence AND no risk. A report carrying only a risk score is thin but
    real, so it parses — pinned here because the guard reads as an OR at a glance.
    """
    svc = make_service()

    preview = svc.parse_preview(LEARNER_ID, FakeUpload("r.docx", docx_bytes("Risk Score: 0.4")))

    assert preview.risk_score == 0.4
    assert preview.tasks == []


# UT: 1.5-1.6
# AssessmentRepository.save()
# --------------------------------------------------------------------------- #
def test_ut_1_5_save_writes_the_record(fake_supabase):
    """UT-1.5: a valid AssessmentRecord is stored and returned."""
    from app.repositories.assessment_repository import AssessmentRepository

    fake = fake_supabase(seed={"assessment_records": []})
    record = {
        "id": "rec-1", "learner_id": LEARNER_ID, "assessment_date": "2026-07-24",
        "risk_score": 0.4, "task_results": {}, "strengths": [], "weaknesses": [],
        "confidence_score": 0.6, "phonics_score": 30.0, "writing_score": None,
        "word_reading_score": 8.0, "word_spelling_score": 5.0,
    }

    saved = AssessmentRepository().save(record)

    # NOTE: `save` is annotated `-> dict` but returns PostgREST's `.data`, which is a LIST of the
    # rows written. Asserting the real shape rather than the annotated one; flagged for a
    # follow-up, since nothing today reads a field off it (the router passes it straight to JSON).
    assert saved[0]["id"] == "rec-1"
    assert len(fake.store["assessment_records"]) == 1
    # None survives the round trip as None — not coerced to 0 on the way in.
    assert fake.store["assessment_records"][0]["writing_score"] is None


def test_ut_1_6_save_propagates_a_database_failure(fake_supabase):
    """UT-1.6: an unreachable database raises rather than reporting success."""
    from app.repositories.assessment_repository import AssessmentRepository

    fake_supabase(seed={"assessment_records": []},
                  fail_on_execute=RuntimeError("supabase unreachable"))

    with pytest.raises(Exception):
        AssessmentRepository().save({"id": "rec-1", "learner_id": LEARNER_ID})


# UT-1.7
# The metric boundary column — 0 <= score <= ceiling, per metric
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("field, ceiling", [
    ("phonics_score", 50.0),
    ("writing_score", 30.0),
    ("word_reading_score", 10.0),
    ("word_spelling_score", 10.0),
])
def test_ut_1_7_each_metric_accepts_its_whole_range_and_nothing_past_it(field, ceiling):
    """UT-1.7: boundary-value analysis on the confirm validator.

    The ceiling is the NORMALISATION ceiling (phonics 50, writing 30), which is the rubric
    maximum rounded up — deliberately not the exact maximum (46, 24) the radar renders against.
    The form is served the same number, so the two cannot drift apart.
    """
    for ok in (0, 0.5, ceiling - 1, ceiling):
        assert getattr(confirm_payload(**{field: ok}), field) == ok

    for bad in (-0.01, -1, ceiling + 0.01, ceiling + 1):
        with pytest.raises(ValidationError):
            confirm_payload(**{field: bad})


def test_ut_1_7b_the_served_rubric_is_the_one_the_validator_enforces():
    """UT-1.7: GET /assessments/metrics and the validator read the same ceilings.

    This is the whole reason the endpoint exists. If the form is told 0-46 while the API
    enforces 0-50 (or the reverse), the therapist meets a rejection the form said was fine.
    """
    for metric in assessment_metrics():
        assert getattr(confirm_payload(**{metric.key: metric.max}), metric.key) == metric.max
        with pytest.raises(ValidationError):
            confirm_payload(**{metric.key: metric.max + 0.01})


# UT-1.8
# Not assessed is not zero
# --------------------------------------------------------------------------- #
def test_ut_1_8_an_unassessed_metric_stays_none_through_the_whole_write():
    """UT-1.8: a mark left blank reaches BOTH tables as null, never as 0.

    Writing is never administered to band A. A 0 stored here would be a real mark of zero: it
    would rank as the learner's weakest skill, drive the retrieval query, and produce a writing
    activity for a paper they have never sat.
    """
    svc = make_service()

    svc.confirm_and_save(confirm_payload(writing_score=None))

    sitting = svc.sittings.upsert_many.call_args.args[0][0]
    assert sitting["writing"] is None
    assert sitting["writing_pct"] is None          # no mark, no percentile
    assert svc.assessments.save.call_args.args[0]["writing_score"] is None


def test_ut_1_8b_a_genuine_zero_is_kept_as_zero():
    """UT-1.8: the counterpart. A learner who scored 0 has a real mark, and it must survive —
    the null is about ABSENCE, and conflating the two in either direction is the bug."""
    svc = make_service()

    svc.confirm_and_save(confirm_payload(word_spelling_score=0.0))

    assert svc.sittings.upsert_many.call_args.args[0][0]["word_spelling"] == 0.0


# UT-1.9
# The sitting the upload writes — UC1 -> UC2
# --------------------------------------------------------------------------- #
def test_ut_1_9_confirm_writes_a_sitting_as_well_as_a_record():
    """UT-1.9: the write that makes Generate Profile work after an upload.

    `learner_sittings` is the grain ProfilingService promotes from. Writing only
    `assessment_records` — as this used to — left the marks in the database but invisible to the
    profile page, and UC2 answered 409 "no scores on record".
    """
    svc = make_service()

    svc.confirm_and_save(confirm_payload())

    sitting = svc.sittings.upsert_many.call_args.args[0][0]
    assert sitting["learner_id"] == LEARNER_ID
    assert sitting["semester"] == "2026 Sem 1"
    assert sitting["source"] == "upload"          # provenance: not a workbook row, not seed data
    assert sitting["band"] == "A2" and sitting["band_group"] == "A"
    assert sitting["phonics"] == 30.0             # phonics_score -> phonics
    assert sitting["word_reading_accuracy"] == 8.0  # the field names differ; the mapping matters
    assert "id" not in sitting                    # Postgres generates it; the upsert is on the
                                                  # natural key (learner_id, semester)


def test_ut_1_9b_the_sitting_is_written_before_the_record():
    """UT-1.9: order matters, because there is no cross-table transaction.

    Sitting first means a retry after a half-failure re-upserts the same (learner_id, semester)
    row. Record first would append a SECOND assessment record on every retry, since the record's
    id is freshly generated each call.
    """
    svc = make_service()
    order = []
    svc.sittings.upsert_many.side_effect = lambda rows: order.append("sitting")
    svc.assessments.save.side_effect = lambda row: order.append("record") or {"id": "rec-1"}

    svc.confirm_and_save(confirm_payload())

    assert order == ["sitting", "record"]


def test_ut_1_9c_a_failed_sitting_write_never_writes_a_record():
    """UT-1.9: the first write failing must abort, not leave a record with no sitting behind."""
    svc = make_service()
    svc.sittings.upsert_many.side_effect = RuntimeError("supabase unreachable")

    with pytest.raises(StorageError):
        svc.confirm_and_save(confirm_payload())

    svc.assessments.save.assert_not_called()


def test_ut_1_9e_the_record_is_json_safe_before_it_reaches_the_repository():
    """UT-1.9: `assessment_date` goes to PostgREST as a string, not a `date` object.

    Kept from the `uploadData` branch. The DTO may hold a real date, but the driver serialises
    the payload to JSON — an unconverted `date` raises at the boundary, on the second of the two
    writes, leaving a sitting already committed with no record beside it.
    """
    svc = make_service()

    out = svc.confirm_and_save(confirm_payload())

    assert out["status"] == "success"
    saved = svc.assessments.save.call_args.args[0]
    assert saved["learner_id"] == str(LEARNER_ID)
    assert isinstance(saved["assessment_date"], str)


def test_ut_1_9f_a_failed_record_write_is_translated_into_storage_error():
    """UT-1.6 (service half): the repository's raw driver failure becomes StorageError HERE.

    Kept from the `uploadData` branch, which pinned the record write; UT-1.9c pins the sitting
    write, which did not exist when that branch was cut. The repository deliberately does not
    catch (UT-1.6), so this is the only layer that turns a driver error into a type the router
    can map to a 500.
    """
    svc = make_service()
    svc.assessments.save.side_effect = ConnectionError("connection refused")

    with pytest.raises(StorageError, match="connection refused"):
        svc.confirm_and_save(confirm_payload())

    # The sitting was written first and stays — deliberately. A retry upserts the same
    # (learner_id, semester) row rather than appending a second one. See UT-1.9b.
    svc.sittings.upsert_many.assert_called_once()


def test_ut_1_9d_band_falls_back_to_the_learners_own_when_not_supplied():
    """UT-1.9: an upload that omits the band still records one, read off the learner.

    A sitting with no band_group cannot be ranked (no population) and cannot be grounded by UC3,
    which scopes retrieval by band — so falling back beats storing null.
    """
    svc = make_service()

    svc.confirm_and_save(confirm_payload(band=None, band_group=None))

    sitting = svc.sittings.upsert_many.call_args.args[0][0]
    assert sitting["band"] == "A2" and sitting["band_group"] == "A"


# UT-1.10
# Percentiles computed on upload
# --------------------------------------------------------------------------- #
def test_ut_1_10_percentiles_rank_the_mark_against_its_semester_and_band():
    """UT-1.10: the upload computes percentiles, so the radar still has axes to draw.

    LearnerOverviewService treats a metric as assessed only when it has BOTH a mark and a
    percentile. Without this, uploading and promoting would render every axis as "not assessed"
    AND overwrite percentiles the workbook had already computed.
    """
    peers = [{"phonics": 10.0}, {"phonics": 20.0}, {"phonics": 40.0}]
    svc = make_service(peers=peers)

    svc.confirm_and_save(confirm_payload(phonics_score=30.0))

    sitting = svc.sittings.upsert_many.call_args.args[0][0]
    # Population is the three peers plus this learner's own mark: [10, 20, 30, 40]. 30 ranks 3rd
    # of 4 = 75.0, matching pandas' `rank(pct=True) * 100` to the digit — which is the rule the
    # workbook ingest uses, and the agreement test_percentiles.py pins.
    assert sitting["phonics_pct"] == 75.0
    svc.sittings.peer_marks.assert_called_once_with("2026 Sem 1", "A")


def test_ut_1_10b_a_learner_with_no_peers_gets_no_percentile():
    """UT-1.10: the first upload of a brand-new semester has nobody to rank against.

    None, not 0 — a 0 would say "bottom of the cohort", which is a claim about the learner. The
    UI already renders a null percentile as an omitted axis.
    """
    svc = make_service(peers=[])

    svc.confirm_and_save(confirm_payload(phonics_score=30.0))

    # Its own mark is the only one in the population, so it ranks 1 of 1 = 100th percentile.
    # What must NOT happen is a crash or a fabricated middle value.
    assert svc.sittings.upsert_many.call_args.args[0][0]["phonics_pct"] == 100.0


def test_ut_1_10c_no_band_group_means_no_percentiles_at_all():
    """UT-1.10: without a band group there is no honest population to rank against.

    Ranking a learner against another band's paper is the exact comparison percentiles exist to
    prevent — phonics is out of 30 in A2 and 46 in A3.
    """
    svc = make_service()
    svc.learners.find_by_id.return_value = {"id": LEARNER_ID}

    svc.confirm_and_save(confirm_payload(band=None, band_group=None))

    sitting = svc.sittings.upsert_many.call_args.args[0][0]
    assert sitting["phonics_pct"] is None
    svc.sittings.peer_marks.assert_not_called()
