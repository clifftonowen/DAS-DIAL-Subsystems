"""UNIT — ProfilingService, what "Generate Profile" means now (UC2).

    AB2.22  ProfilingService.generate_profile()  UT-2.61, UT-2.62
    AB2.23  ProfilingService.list_sittings()     UT-2.63

SUPERSEDES UT-2.1..UT-2.11 and their `analyse()` bar. Those covered ProfilingAlgorithm deriving
seven cognitive dimensions from `assessment_records.task_results` by keyword, and the
EmptyDataError / NoPatternError branches of the UC2 sequence diagram. The dimensions were mock
scaffolding; the system standardises on the four marks DAS measures, so there is no derivation
left to test — only a promotion.

WHAT THE PROMOTION IS FOR. The ingest already writes the newest workbook sitting onto
`learners`, so on the face of it this does nothing. It exists for the OTHER writer: UC1's upload
appends a sitting at any time, and this is what pulls it through to the dashboard, the radar
chart and activity generation. Both paths land in `learner_sittings`; this is the one place that
reads the newest and makes it current.
"""
import pytest

from app.services.profiling_service import NoScoresError, ProfilingService

pytestmark = pytest.mark.unit

LEARNER_ID = "11111111-1111-1111-1111-111111111111"


def sitting(semester="2026 Sem 1", **overrides):
    return {
        "id": f"s-{semester}", "learner_id": LEARNER_ID, "semester": semester,
        "band": "A2", "band_group": "A", "source": "workbook",
        "phonics": 31.0, "word_reading_accuracy": 7.0, "word_spelling": 5.0, "writing": None,
        "writing_genre": None,
        "phonics_pct": 68.4, "word_reading_accuracy_pct": 41.0,
        "word_spelling_pct": 33.2, "writing_pct": None,
        **overrides,
    }


@pytest.fixture
def service(monkeypatch):
    """The service with both repositories stubbed, capturing what it would write."""
    svc = ProfilingService()
    saved = []

    def wire(latest=None):
        monkeypatch.setattr(svc.sittings, "latest_for_learner", lambda _id: latest)
        monkeypatch.setattr(svc.learners, "save", lambda row: saved.append(row) or row)
        return svc, saved

    return wire


# ── the promotion ─────────────────────────────────────────────────────────────
def test_promotes_the_newest_sitting_onto_the_learner(service):
    """UT-2.61: the marks and their percentiles become the learner's current values."""
    svc, saved = service(sitting())

    svc.generate_profile(LEARNER_ID)

    assert len(saved) == 1
    written = saved[0]
    assert written["id"] == LEARNER_ID, "the learner is updated, not a new row inserted"
    assert written["phonics"] == 31.0
    assert written["phonics_pct"] == 68.4
    assert written["semester"] == "2026 Sem 1"


def test_the_band_travels_with_the_marks(service):
    """UT-2.61: a mark is meaningless without the paper it was scored against.

    Phonics is out of 30 in band A2 and 46 in A3, so promoting the marks while leaving a stale
    band would render the radar chart against the wrong rubric.
    """
    svc, saved = service(sitting(band="A3", band_group="A"))

    svc.generate_profile(LEARNER_ID)

    assert saved[0]["band"] == "A3"
    assert saved[0]["band_group"] == "A"


def test_the_sittings_own_identity_is_never_written(service):
    """UT-2.61: `id` is the LEARNER's, and `learner_id` is not a column on `learners`.

    Copying the sitting's own id across would overwrite the learner's primary key with it —
    orphaning every activity, assessment record and sitting that points at the old one.
    """
    svc, saved = service(sitting())

    svc.generate_profile(LEARNER_ID)

    assert saved[0]["id"] == LEARNER_ID
    assert "learner_id" not in saved[0]
    assert "source" not in saved[0], "provenance belongs to the sitting, not the learner"


def test_identity_columns_are_never_touched(service):
    """UT-2.61: promoting scores must not rewrite who the learner is.

    `pseudonym`, `tier` and `on_caseload` are not in the payload at all, so an upsert leaves
    them alone. Present in the payload — even as None — they would be blanked.
    """
    svc, saved = service(sitting())

    svc.generate_profile(LEARNER_ID)

    for protected in ("pseudonym", "tier", "on_caseload", "student_id"):
        assert protected not in saved[0]


def test_running_it_twice_is_idempotent(service):
    """UT-2.61: the button is safe to press.

    Pressing it is how a therapist pulls through an assessment someone else just uploaded, so
    it has to be harmless when nothing has changed.
    """
    svc, saved = service(sitting())

    svc.generate_profile(LEARNER_ID)
    svc.generate_profile(LEARNER_ID)

    assert saved[0] == saved[1]


# ── no scores ─────────────────────────────────────────────────────────────────
def test_a_learner_with_no_sittings_raises_no_scores(service):
    """UT-2.62: the one failure, and it is not really a failure.

    A learner added in the app has never been assessed. That is not a profiling error the
    therapist can retry out of — it is the cue to upload an assessment, which is why it has its
    own type and becomes a 409 rather than a bare 404.
    """
    svc, saved = service(None)

    with pytest.raises(NoScoresError):
        svc.generate_profile(LEARNER_ID)

    assert saved == [], "nothing is written when there is nothing to promote"


def test_the_error_names_the_learner(service):
    """UT-2.62: the message reaches the client as the 409 detail."""
    svc, _ = service(None)

    with pytest.raises(NoScoresError, match=LEARNER_ID):
        svc.generate_profile(LEARNER_ID)


# ── the history ───────────────────────────────────────────────────────────────
def test_list_sittings_delegates_to_the_repository(monkeypatch):
    """UT-2.63: the chart's series, in the repository's order.

    The service does NOT re-sort. `semester` sorts chronologically as text and the repository
    already ordered on it; sorting again here would be a second place to get it wrong.
    """
    svc = ProfilingService()
    monkeypatch.setattr(
        svc.sittings, "list_by_learner",
        lambda _id: [sitting("2022 Sem 1"), sitting("2026 Sem 1")],
    )

    assert [s["semester"] for s in svc.list_sittings(LEARNER_ID)] == [
        "2022 Sem 1", "2026 Sem 1"]
