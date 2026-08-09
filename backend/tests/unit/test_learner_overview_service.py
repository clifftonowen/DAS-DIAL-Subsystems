"""UNIT — LearnerOverviewService, the composition behind LearnerDetailPage (UC2).

    AB2.14  LearnerOverviewService.get_overview()   UT-2.37, UT-2.38
    AB2.15  LearnerOverviewService._metrics()       UT-2.39, UT-2.40

(AB2.13 and UT-2.27..UT-2.36 belong to the frontend bar — frontend/src/components/__tests__/
Graph.test.jsx — so this file continues past them rather than reusing them.)

Extends the PM3 UC2 test plan (see test_profiling_algorithm_cluster.py for why).

The service under test with both repositories stubbed, so what is being checked is the
composition: which side each field comes from, and — the part that carries a clinical claim —
which marks are `assessed`.

THE CENTRAL CASE IS PARTIAL DATA. The learner row carries their CURRENT marks and
`learner_sittings` carries the history, and either can be absent:

    from the workbook   marks and up to ten sittings
    added in the app    neither, until someone uploads an assessment for them

A learner with exactly ONE sitting is as normal as one with ten — it renders as a point rather
than a line. Only an unknown learner raises.
"""
import pytest

from app.services.learner_overview_service import (
    LearnerNotFoundError,
    LearnerOverviewService,
)

pytestmark = pytest.mark.unit

LEARNER_ID = "11111111-1111-1111-1111-111111111111"


def learner(**overrides):
    """A caseload learner who is also in the workbook: identity AND marks on one row."""
    return {
        "id": LEARNER_ID, "student_id": "Student 0142", "pseudonym": "Aisha Binti Rahman",
        "tier": "Tier 2", "on_caseload": True,
        "semester": "2026 Sem 1", "band": "A2", "band_group": "A",
        "cluster_band": "A 3", "cluster_cohort": "Cohort 2",
        "phonics": 31.0, "word_reading_accuracy": 7.0, "word_spelling": 5.0, "writing": None,
        "phonics_pct": 68.4, "word_reading_accuracy_pct": 41.0,
        "word_spelling_pct": 33.2, "writing_pct": None,
        **overrides,
    }


def cohort_learner(**overrides):
    """Anonymised research data: the same marks, no name, not on the caseload."""
    return learner(pseudonym="", tier="", on_caseload=False, **overrides)


def sitting(semester="2026 Sem 1", **overrides):
    """One row of the learner's history."""
    return {
        "learner_id": LEARNER_ID, "semester": semester, "band": "A2", "band_group": "A",
        "source": "workbook",
        "phonics": 31.0, "word_reading_accuracy": 7.0, "word_spelling": 5.0, "writing": None,
        "phonics_pct": 68.4, "word_reading_accuracy_pct": 41.0,
        "word_spelling_pct": 33.2, "writing_pct": None,
        **overrides,
    }


@pytest.fixture
def service(monkeypatch):
    """The service with both repositories stubbed. `wire` sets what each returns."""
    svc = LearnerOverviewService()

    def wire(learner_row=None, history=None):
        monkeypatch.setattr(svc.learners, "find_by_id", lambda _id: learner_row)
        monkeypatch.setattr(svc.sittings, "list_by_learner", lambda _id: history or [])
        return svc

    return wire


# ── both sides present ────────────────────────────────────────────────────────
def test_composes_identity_current_marks_and_history(service):
    """UT-2.37: everything the page renders, in one payload."""
    out = service(learner(), [sitting("2025 Sem 1"), sitting("2026 Sem 1")]).get_overview(LEARNER_ID)

    assert out.pseudonym == "Aisha Binti Rahman"
    assert out.on_caseload is True
    assert out.band == "A2"
    assert out.student_id == "Student 0142"
    assert out.semester == "2026 Sem 1"
    assert out.cluster_cohort == "Cohort 2"
    assert [p.semester for p in out.history] == ["2025 Sem 1", "2026 Sem 1"]


def test_history_preserves_the_repository_order(service):
    """UT-2.37: oldest first, because that is the order the chart plots left to right.

    The service must not re-sort: `semester` sorts chronologically as text and the repository
    already ordered on it, so a second sort here would be a second place to get it wrong.
    """
    out = service(learner(), [sitting("2022 Sem 1"), sitting("2024 Sem 2"),
                              sitting("2026 Sem 1")]).get_overview(LEARNER_ID)

    assert [p.semester for p in out.history] == ["2022 Sem 1", "2024 Sem 2", "2026 Sem 1"]


def test_history_carries_raw_marks_and_percentiles_together(service):
    """UT-2.37: the chart's scale toggle needs both on every point.

    Switching Raw <-> Percentile must not cost a round trip, and the two answer different
    questions — the awarded mark versus where it ranks.
    """
    point = service(learner(), [sitting()]).get_overview(LEARNER_ID).history[0]

    assert point.phonics == 31.0
    assert point.phonics_pct == 68.4
    assert point.band == "A2", "the paper this mark was scored against, which can change"


def test_metrics_carry_both_the_mark_and_its_rank(service):
    """UT-2.39: each metric holds the raw mark, its rubric max and the percentile.

    All three, not one: the radar's radius needs the percentile (the four rubrics are not
    comparable), while the therapist reads the mark that was awarded. Dropping either would
    make one of the two unavailable to the UI.
    """
    out = service(learner(), [sitting()]).get_overview(LEARNER_ID)
    phonics = next(m for m in out.metrics if m.key == "phonics")

    assert (phonics.raw, phonics.max, phonics.percentile) == (31.0, 46.0, 68.4)
    assert phonics.label == "Phonics"
    assert phonics.assessed is True


def test_all_four_features_are_returned_even_when_unassessed(service):
    """UT-2.39: the metric list is the full feature set, not just the scored ones.

    The chart needs to name what was omitted ("Writing not assessed"), which it cannot do from
    a list that silently drops it.
    """
    out = service(learner(), [sitting()]).get_overview(LEARNER_ID)

    assert [m.key for m in out.metrics] == [
        "phonics", "word_reading_accuracy", "word_spelling", "writing"]


def test_a_paper_the_learner_never_sat_is_not_assessed(service):
    """UT-2.40: writing is absent for band A, and absent is not zero.

    The distinction the radar chart turns on. `assessed=False` drops the axis; a 0 would draw
    the learner at the bottom of a paper that was never administered to them.
    """
    out = service(learner(), [sitting()]).get_overview(LEARNER_ID)
    writing = next(m for m in out.metrics if m.key == "writing")

    assert writing.assessed is False
    assert writing.raw is None and writing.percentile is None
    assert writing.max == 24.0, "the rubric ceiling is known even when the mark is not"


def test_a_mark_with_no_percentile_is_not_plottable(service):
    """UT-2.40: a mark stored before the percentile columns existed cannot be plotted.

    It still reaches the client — the legend can show 31/46 — but the radar has no radius for
    it, so `assessed` is False rather than plotting it against an invented rank.
    """
    out = service(learner(phonics_pct=None), [sitting()]).get_overview(LEARNER_ID)
    phonics = next(m for m in out.metrics if m.key == "phonics")

    assert phonics.raw == 31.0
    assert phonics.percentile is None
    assert phonics.assessed is False


# ── one side missing ──────────────────────────────────────────────────────────
def test_a_learner_created_in_the_app_has_no_marks(service):
    """UT-2.38: never having been in the DIAL workbook is ordinary, not an error.

    A therapist can add a learner who was never assessed by DAS. They have no marks and no
    history until an upload gives them one — and the page must render the upload prompt rather
    than fail.
    """
    bare = {"id": LEARNER_ID, "pseudonym": "New Learner", "tier": "Tier 1", "on_caseload": True}
    out = service(bare, []).get_overview(LEARNER_ID)

    assert out.student_id is None and out.band_group is None
    assert all(not m.assessed for m in out.metrics)
    assert out.history == []
    assert out.pseudonym == "New Learner", "identity survives with no scores at all"


def test_the_metric_list_is_complete_even_with_no_marks(service):
    """UT-2.39: all four features travel even when none was assessed.

    The chart names what it omitted, which it cannot do from a list that dropped it — so an
    empty list and four unassessed metrics are NOT interchangeable.
    """
    bare = {"id": LEARNER_ID, "pseudonym": "New Learner", "on_caseload": True}
    out = service(bare, []).get_overview(LEARNER_ID)

    assert [m.key for m in out.metrics] == [
        "phonics", "word_reading_accuracy", "word_spelling", "writing"]


def test_a_cohort_learner_is_marked_not_on_the_caseload(service):
    """UT-2.38: the flag is informational, and does not restrict anything.

    A research-cohort learner has the same four marks as anyone else, so their page offers the
    same actions. `on_caseload` drives a badge and nothing more — it used to gate the whole
    page, and this is what pins that it no longer does.
    """
    out = service(cohort_learner(), [sitting()]).get_overview(LEARNER_ID)

    assert out.on_caseload is False
    assert out.pseudonym == ""
    assert len([m for m in out.metrics if m.assessed]) == 3, "their marks still show"
    assert len(out.history) == 1, "and so does their history"


def test_a_learner_with_neither_is_still_a_learner(service):
    """UT-2.38: identity survives when both optional sides are missing."""
    bare = {"id": LEARNER_ID, "pseudonym": "New Learner", "on_caseload": True}
    out = service(bare, []).get_overview(LEARNER_ID)

    assert out.learner_id == LEARNER_ID
    assert out.pseudonym == "New Learner"
    assert out.history == []
    assert all(not m.assessed for m in out.metrics)


def test_an_unknown_learner_raises(service):
    """UT-2.37: the one lookup whose absence is an error.

    Distinct from the two above: a missing profile or cohort link is something the therapist
    can act on from the page, whereas an unknown learner means the id itself is wrong.
    """
    with pytest.raises(LearnerNotFoundError):
        service(None, [sitting()]).get_overview("nope")
