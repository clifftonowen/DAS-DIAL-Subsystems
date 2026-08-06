"""UNIT — LearnerSittingRepository in isolation (UC2).

    AB2.24  LearnerSittingRepository  UT-2.64, UT-2.65

One repository method at a time, with the driver replaced by FakeSupabase.

WHAT THIS TABLE IS FOR. One row per learner per semester — the score history behind the profile
page's line chart, and the meeting point of the system's two writers: the workbook ingest and
UC1's upload. Both upsert here on `(learner_id, semester)`, and ProfilingService promotes
whichever is newest. Get the key or the ordering wrong and the chart plots the wrong shape with
no error anywhere.
"""
import pytest

from app.repositories.learner_sitting_repository import LearnerSittingRepository

pytestmark = pytest.mark.unit

LEARNER = "11111111-1111-1111-1111-111111111111"
OTHER = "22222222-2222-2222-2222-222222222222"


def sitting(learner_id=LEARNER, semester="2026 Sem 1", **overrides):
    return {
        "id": f"s-{learner_id}-{semester}", "learner_id": learner_id, "semester": semester,
        "band": "A2", "band_group": "A", "source": "workbook",
        "phonics": 31.0, "word_reading_accuracy": 7.0, "word_spelling": 5.0, "writing": None,
        "phonics_pct": 68.4, "word_reading_accuracy_pct": 41.0,
        "word_spelling_pct": 33.2, "writing_pct": None,
        **overrides,
    }


# ── reads ─────────────────────────────────────────────────────────────────────
def test_history_comes_back_oldest_first(fake_supabase):
    """UT-2.64: the order the chart plots left to right.

    `semester` sorts chronologically as plain text for every value in the workbook — '2022 Sem
    1' < '2022 Sem 2' < '2023 Sem 1' — which is what lets a text sort stand in for a date.
    """
    fake_supabase(seed={"learner_sittings": [
        sitting(semester="2026 Sem 1"),
        sitting(semester="2022 Sem 1"),
        sitting(semester="2024 Sem 2"),
    ]})

    rows = LearnerSittingRepository().list_by_learner(LEARNER)

    assert [r["semester"] for r in rows] == ["2022 Sem 1", "2024 Sem 2", "2026 Sem 1"]


def test_history_is_scoped_to_one_learner(fake_supabase):
    """UT-2.64: a shared table, so the filter is what keeps one learner's line their own."""
    fake_supabase(seed={"learner_sittings": [
        sitting(LEARNER, "2026 Sem 1"),
        sitting(OTHER, "2026 Sem 1"),
        sitting(OTHER, "2025 Sem 1"),
    ]})

    assert len(LearnerSittingRepository().list_by_learner(LEARNER)) == 1


def test_a_learner_with_no_sittings_gets_an_empty_list(fake_supabase):
    """UT-2.64: never assessed is an ordinary state, not an error.

    It is what the profile page turns into the upload prompt, so it must not raise.
    """
    fake_supabase(seed={"learner_sittings": []})

    assert LearnerSittingRepository().list_by_learner(LEARNER) == []


def test_latest_is_the_most_recent_semester(fake_supabase):
    """UT-2.64: what Generate Profile promotes.

    Newest by SEMESTER, not by insertion order — the ingest writes the workbook in whatever
    order it batched, and UC1 can append a sitting for an earlier semester at any time.
    """
    fake_supabase(seed={"learner_sittings": [
        sitting(semester="2022 Sem 1", phonics=10.0),
        sitting(semester="2026 Sem 1", phonics=31.0),
        sitting(semester="2024 Sem 2", phonics=20.0),
    ]})

    assert LearnerSittingRepository().latest_for_learner(LEARNER)["phonics"] == 31.0


def test_latest_is_none_when_there_are_no_sittings(fake_supabase):
    """UT-2.64: None is what becomes NoScoresError, so it must not raise here."""
    fake_supabase(seed={"learner_sittings": []})

    assert LearnerSittingRepository().latest_for_learner(LEARNER) is None


# ── writes ────────────────────────────────────────────────────────────────────
def test_upsert_conflicts_on_learner_and_semester(fake_supabase):
    """UT-2.65: THE KEY THAT STOPS THE CHART DUPLICATING.

    A learner sits a given semester once. Conflicting on the generated `id` instead would append
    a second row on every re-ingest, and the line chart would show ten points where there is one
    semester — with no error to say why.
    """
    fake = fake_supabase(seed={"learner_sittings": [sitting(phonics=20.0)]})

    LearnerSittingRepository().upsert_many([sitting(phonics=31.0)])

    rows = fake.store["learner_sittings"]
    assert len(rows) == 1, "a second row means the upsert conflicted on the wrong column"
    assert rows[0]["phonics"] == 31.0


def test_the_same_semester_for_two_learners_is_two_rows(fake_supabase):
    """UT-2.65: the key is the PAIR — semester alone would collapse the whole cohort.

    Every one of the 5,783 students has a 2026 Sem 1 row; keying on semester alone would leave
    one sitting in the table for the entire year.
    """
    fake = fake_supabase(seed={"learner_sittings": []})

    LearnerSittingRepository().upsert_many([
        sitting(LEARNER, "2026 Sem 1"),
        sitting(OTHER, "2026 Sem 1"),
    ])

    assert len(fake.store["learner_sittings"]) == 2


def test_a_new_semester_appends_rather_than_replacing(fake_supabase):
    """UT-2.65: history accumulates. This is the whole point of the table."""
    fake = fake_supabase(seed={"learner_sittings": [sitting(semester="2025 Sem 1")]})

    LearnerSittingRepository().upsert_many([sitting(semester="2026 Sem 1")])

    assert len(fake.store["learner_sittings"]) == 2


def test_upsert_batches_large_payloads(fake_supabase):
    """UT-2.65: ~22,892 rows in one request exceeds Supabase's payload limit."""
    fake = fake_supabase(seed={"learner_sittings": []})
    rows = [sitting(f"uuid-{i}", "2026 Sem 1") for i in range(1200)]

    LearnerSittingRepository().upsert_many(rows, batch=500)

    assert len(fake.store["learner_sittings"]) == 1200
    assert len(fake.queries_on("learner_sittings")) == 3, "1200 rows in batches of 500"
