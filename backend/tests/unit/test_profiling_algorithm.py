"""UNIT — ProfilingAlgorithm.analyse() in isolation (UC2, activation bar AB2.5).

    AB2.5  ProfilingAlgorithm.analyse()   UT-2.8 (valid), UT-2.9 (invalid)

Pure function: assessment records in, seven dimension scores out. No repository,
no Supabase, no LLM — the algorithm is deterministic by design.

Clustering — `cluster()` and `cluster_by_group()`, the algorithm's other half — is
covered separately in test_profiling_algorithm_cluster.py (UT-2.12 .. UT-2.24).
"""
import pytest

from app.agents.profiling_algorithm import (
    DIMENSIONS, NEUTRAL, NoPatternError, ProfilingAlgorithm)

pytestmark = pytest.mark.unit


def record(date, tasks):
    return {"assessment_date": date, "task_results": tasks}


def test_returns_exactly_the_seven_profile_columns():
    """UT-2.8: ProfilingService writes this dict straight to learner_profiles, so an extra
    key would be a Supabase "column does not exist" error."""
    result = ProfilingAlgorithm().analyse([
        record("2026-07-01", {"Phoneme Segmentation": {"score": 3, "max_score": 10}}),
    ])
    assert set(result) == set(DIMENSIONS)


def test_no_records_raises_no_pattern_error():
    """UT-2.9: nothing to analyse is not a seven-way NEUTRAL profile.

    Returning all-NEUTRAL here would render as a complete radar chart sitting at exactly
    50% on every axis — a confident-looking statement about a learner we know nothing
    about. In the real flow ProfilingService raises EmptyDataError before reaching this
    point; the guard exists so the algorithm is safe called directly.
    """
    with pytest.raises(NoPatternError):
        ProfilingAlgorithm().analyse([])


def test_normalises_score_over_max_score():
    result = ProfilingAlgorithm().analyse([
        record("2026-07-01", {"Phoneme Segmentation": {"score": 3, "max_score": 10}}),
    ])
    assert result["phonological_processing"] == 0.3


def test_averages_several_tasks_feeding_one_dimension():
    result = ProfilingAlgorithm().analyse([
        record("2026-07-01", {
            "Phoneme Segmentation": {"score": 2, "max_score": 10},   # 0.2
            "Rhyme Detection": {"score": 8, "max_score": 10},        # 0.8
        }),
    ])
    assert result["phonological_processing"] == 0.5


def test_dimension_without_evidence_stays_neutral():
    result = ProfilingAlgorithm().analyse([
        record("2026-07-01", {"Spelling Dictation": {"score": 1, "max_score": 10}}),
    ])
    assert result["spelling"] == 0.1
    assert result["comprehension"] == NEUTRAL


def test_unrecognised_task_names_are_ignored_not_misattributed():
    """A task we cannot route contributes to nothing — it must not leak into a dimension
    that merely looks similar. "Handwriting Neatness" measures motor skill, and scoring
    spelling 0.0 from it would put a learner in an intervention they do not need.

    Paired here with a recognised task so the assertion is about routing rather than about
    the empty-evidence guard, which UT-2.9 covers.
    """
    result = ProfilingAlgorithm().analyse([
        record("2026-07-01", {
            "Handwriting Neatness": {"score": 0, "max_score": 10},   # unroutable
            "Phoneme Segmentation": {"score": 6, "max_score": 10},   # phonological only
        }),
    ])
    assert result["phonological_processing"] == 0.6
    assert result["spelling"] == NEUTRAL
    assert result["visualisation"] == NEUTRAL


def test_records_evidencing_nothing_raise_rather_than_read_as_neutral():
    """UT-2.9: records exist, but not one task could be routed or scored.

    The ST-2.3 branch — "assessment records with no identifiable learning patterns".
    """
    with pytest.raises(NoPatternError):
        ProfilingAlgorithm().analyse([
            record("2026-07-01", {"Handwriting Neatness": {"score": 0, "max_score": 10}}),
        ])


def test_newest_record_wins_for_a_dimension_it_evidences():
    result = ProfilingAlgorithm().analyse([
        record("2026-01-01", {"Phoneme Segmentation": {"score": 2, "max_score": 10}}),
        record("2026-07-01", {"Phoneme Segmentation": {"score": 9, "max_score": 10}}),
    ])
    assert result["phonological_processing"] == 0.9


def test_older_record_fills_a_dimension_the_newest_does_not_cover():
    result = ProfilingAlgorithm().analyse([
        record("2026-01-01", {"Reading Comprehension": {"score": 4, "max_score": 10}}),
        record("2026-07-01", {"Phoneme Segmentation": {"score": 9, "max_score": 10}}),
    ])
    assert result["phonological_processing"] == 0.9   # newest
    assert result["comprehension"] == 0.4             # carried from the older sitting


def test_zero_max_score_does_not_divide_by_zero():
    # The unscorable task is skipped rather than crashing the run. A second, scorable task
    # keeps the record as a whole evidenced, so this asserts the divide-by-zero guard and
    # not the empty-evidence guard.
    result = ProfilingAlgorithm().analyse([
        record("2026-07-01", {
            "Phoneme Segmentation": {"score": 5, "max_score": 0},    # unscorable
            "Written Spelling": {"score": 4, "max_score": 10},
        }),
    ])
    assert result["phonological_processing"] == NEUTRAL
    assert result["spelling"] == 0.4


def test_scores_are_clamped_into_0_1():
    result = ProfilingAlgorithm().analyse([
        record("2026-07-01", {"Spelling Test": {"score": 15, "max_score": 10}}),
    ])
    assert result["spelling"] == 1.0


def test_accepts_an_already_normalised_bare_number():
    result = ProfilingAlgorithm().analyse([
        record("2026-07-01", {"Digit Span": 0.25}),
    ])
    assert result["working_memory"] == 0.25


def test_missing_assessment_date_sorts_last_rather_than_raising():
    result = ProfilingAlgorithm().analyse([
        {"task_results": {"Phoneme Segmentation": {"score": 1, "max_score": 10}}},
        record("2026-07-01", {"Phoneme Segmentation": {"score": 7, "max_score": 10}}),
    ])
    assert result["phonological_processing"] == 0.7


def test_a_task_can_evidence_more_than_one_dimension():
    # "Rapid Automatised Naming" is both a naming-speed (executive) and a
    # phonological retrieval measure.
    result = ProfilingAlgorithm().analyse([
        record("2026-07-01", {"Rapid Automatised Naming of Sounds": {"score": 6, "max_score": 10}}),
    ])
    assert result["executive_functioning"] == 0.6
    assert result["phonological_processing"] == 0.6
