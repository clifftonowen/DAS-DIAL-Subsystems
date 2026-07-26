"""UNIT — ProfilingAlgorithm in isolation.

Pure function: assessment records in, seven dimension scores out. No repository,
no Supabase, no LLM — the algorithm is deterministic by design.
"""
import pytest

from app.agents.profiling_algorithm import DIMENSIONS, NEUTRAL, ProfilingAlgorithm

pytestmark = pytest.mark.unit


def record(date, tasks):
    return {"assessment_date": date, "task_results": tasks}


def test_returns_exactly_the_seven_profile_columns():
    # ProfilingService writes this dict straight to learner_profiles, so an extra
    # key would be a Supabase "column does not exist" error.
    result = ProfilingAlgorithm().analyse([])
    assert set(result) == set(DIMENSIONS)


def test_no_records_scores_every_dimension_neutral():
    assert ProfilingAlgorithm().analyse([]) == {dim: NEUTRAL for dim in DIMENSIONS}


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
    result = ProfilingAlgorithm().analyse([
        record("2026-07-01", {"Handwriting Neatness": {"score": 0, "max_score": 10}}),
    ])
    assert result == {dim: NEUTRAL for dim in DIMENSIONS}


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
    result = ProfilingAlgorithm().analyse([
        record("2026-07-01", {"Phoneme Segmentation": {"score": 5, "max_score": 0}}),
    ])
    assert result["phonological_processing"] == NEUTRAL


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
