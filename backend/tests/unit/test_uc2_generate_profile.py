"""UNIT — UC2 Generate Learner Profile.

One test per activation bar of the UC2 sequence diagram, every collaborator mocked.
Bars, in right-to-left diagram order:

    AB2.2  ProfileController.generateProfile        UT-2.1, UT-2.2
    AB2.3  ProfilingService.generateProfile         UT-2.3, UT-2.4, UT-2.5
    AB2.4  AssessmentRepository.findByLearner       UT-2.6, UT-2.7
    AB2.5  ProfilingAlgorithm.analyse               UT-2.8, UT-2.9   <- test_profiling_algorithm.py
    AB2.6  LearnerProfileRepository.saveProfile     UT-2.10, UT-2.11

AB2.1 (the Dashboard React bar) has no backend test.

AB2.5 lives in its own file because analyse() is a pure function with no collaborators to
mock — nothing in this module's setup applies to it.

The three failure branches under test are the three `alt` blocks of the sequence diagram:
EmptyDataError (flow 2a), ProfileGenerationError via NoPatternError (flow 4a), and
StorageError (flows 4a/6a).
"""
import pytest
from unittest.mock import Mock

from app.agents.profiling_algorithm import DIMENSIONS, NEUTRAL, NoPatternError
from app.repositories.assessment_repository import AssessmentRepository
from app.repositories.base import StorageError
from app.repositories.learner_profile_repository import LearnerProfileRepository
from app.routers import profiles as profiles_router
from app.services.profiling_service import (
    EmptyDataError, ProfileGenerationError, ProfilingService)

pytestmark = pytest.mark.unit

LEARNER_ID = "11111111-1111-4111-8111-111111111111"

RECORD = {
    "learner_id": LEARNER_ID,
    "assessment_date": "2026-07-01",
    "task_results": {"Phoneme Segmentation": {"score": 6, "max_score": 10}},
}

METRICS = {dim: NEUTRAL for dim in DIMENSIONS} | {"phonological_processing": 0.6}
PROFILE = {"learner_id": LEARNER_ID, **METRICS}


def a_service(records=None, metrics=None, analyse_raises=None, save_raises=None):
    """A ProfilingService with all three collaborators replaced by mocks (AB2.3)."""
    svc = ProfilingService()
    svc.assessments = Mock(spec=AssessmentRepository)
    svc.assessments.find_by_learner.return_value = [] if records is None else records
    svc.profiles = Mock(spec=LearnerProfileRepository)
    svc.algorithm = Mock()

    if analyse_raises is not None:
        svc.algorithm.analyse.side_effect = analyse_raises
    else:
        svc.algorithm.analyse.return_value = metrics if metrics is not None else METRICS
    if save_raises is not None:
        svc.profiles.save.side_effect = save_raises
    return svc


# --------------------------------------------------------------------------- #
# AB2.2 — ProfileController.generateProfile
# --------------------------------------------------------------------------- #
def test_generate_profile_returns_the_profile(client, auth_ok, monkeypatch):
    """UT-2.1: valid learner id -> 200 and the generated LearnerProfile."""
    generate = Mock(return_value=PROFILE)
    monkeypatch.setattr(profiles_router.svc, "generate_profile", generate)

    resp = client.post(f"/profiles/{LEARNER_ID}")

    assert resp.status_code == 200
    assert resp.json()["learner_id"] == LEARNER_ID
    assert resp.json()["phonological_processing"] == 0.6
    generate.assert_called_once_with(LEARNER_ID)


def test_generate_profile_returns_404_when_the_learner_has_no_records(
        client, auth_ok, monkeypatch):
    """UT-2.2: EmptyDataError -> 404 naming the problem, and no profile in the body.

    Flow 2a. The UI shows "No assessment data for this learner", so the detail has to
    survive into the response rather than being swallowed into a bare status.
    """
    def boom(_learner_id):
        raise EmptyDataError("No assessment records for learner.")

    monkeypatch.setattr(profiles_router.svc, "generate_profile", boom)

    resp = client.post(f"/profiles/{LEARNER_ID}")

    assert resp.status_code == 404
    assert "No assessment records" in resp.json()["detail"]
    assert "phonological_processing" not in resp.json()


def test_generate_profile_distinguishes_its_three_failures_by_status(
        client, auth_ok, monkeypatch):
    """UT-2.2 (boundary): each failure branch gets its own status code.

    The therapist's next action differs per branch — upload an assessment, look at the
    records, or wait for the database — so the UI must be able to tell them apart.
    """
    cases = [
        (EmptyDataError("none"), 404),
        (ProfileGenerationError("no patterns"), 422),
        (StorageError("db down"), 500),
    ]
    for error, expected in cases:
        monkeypatch.setattr(
            profiles_router.svc, "generate_profile",
            Mock(side_effect=error))
        assert client.post(f"/profiles/{LEARNER_ID}").status_code == expected


# --------------------------------------------------------------------------- #
# AB2.3 — ProfilingService.generateProfile
# --------------------------------------------------------------------------- #
def test_service_retrieves_analyses_and_saves():
    """UT-2.3: the happy path takes all three edges, in order, and returns the profile."""
    svc = a_service(records=[RECORD])

    result = svc.generate_profile(LEARNER_ID)

    svc.assessments.find_by_learner.assert_called_once_with(LEARNER_ID)
    svc.algorithm.analyse.assert_called_once_with([RECORD])
    svc.profiles.save.assert_called_once()
    assert result == PROFILE
    # The saved row is exactly what is returned — the dashboard reads back what we stored.
    assert svc.profiles.save.call_args[0][0] == PROFILE


def test_service_raises_empty_data_error_and_takes_no_further_edge():
    """UT-2.4: no records -> EmptyDataError, and the algorithm/save edges are NOT taken.

    Flow 2a says "System aborts profile generation". Aborting means not writing a
    seven-way NEUTRAL profile for a learner nobody has assessed.
    """
    svc = a_service(records=[])

    with pytest.raises(EmptyDataError):
        svc.generate_profile(LEARNER_ID)

    svc.algorithm.analyse.assert_not_called()
    svc.profiles.save.assert_not_called()


def test_service_translates_no_pattern_error_and_saves_nothing():
    """UT-2.5: NoPatternError from the algorithm -> ProfileGenerationError, nothing saved.

    Flow 4a. Translated at the layer boundary so the router never imports the algorithm's
    exception types.
    """
    svc = a_service(records=[RECORD], analyse_raises=NoPatternError("nothing scored"))

    with pytest.raises(ProfileGenerationError):
        svc.generate_profile(LEARNER_ID)

    svc.profiles.save.assert_not_called()


def test_service_lets_a_storage_error_through_untranslated():
    """UT-2.5 (boundary): a failed save is infrastructure, not a data problem.

    StorageError passes through as itself so the router can answer 500 rather than 422 —
    "the database is down" is not the therapist's data being wrong.
    """
    svc = a_service(records=[RECORD], save_raises=StorageError("db down"))

    with pytest.raises(StorageError):
        svc.generate_profile(LEARNER_ID)


# --------------------------------------------------------------------------- #
# AB2.4 — AssessmentRepository.findByLearner
# --------------------------------------------------------------------------- #
def test_find_by_learner_returns_the_records(fake_supabase):
    """UT-2.6: records exist and Supabase is reachable -> the AssessmentRecord list."""
    fake_supabase(seed={"assessment_records": [RECORD]})

    rows = AssessmentRepository().find_by_learner(LEARNER_ID)

    assert len(rows) == 1
    assert rows[0]["learner_id"] == LEARNER_ID


def test_find_by_learner_raises_storage_error_when_supabase_is_unreachable(monkeypatch):
    """UT-2.7: an unreachable client -> StorageError, not the driver's own exception.

    The service must not have to catch httpx/postgrest types to know the read failed.
    """
    repo = AssessmentRepository()
    unreachable = Mock()
    unreachable.select.side_effect = ConnectionError("connection refused")
    monkeypatch.setattr(type(repo), "db", property(lambda _self: unreachable))

    with pytest.raises(StorageError):
        repo.find_by_learner(LEARNER_ID)


def test_no_records_is_an_empty_list_not_a_storage_error(fake_supabase):
    """UT-2.6 (boundary): "this learner has no records" is data, not a fault.

    Collapsing the two would report a network outage as an un-assessed learner, and the
    therapist would be told to upload an assessment that already exists.
    """
    fake_supabase(seed={"assessment_records": []})

    assert AssessmentRepository().find_by_learner(LEARNER_ID) == []


# --------------------------------------------------------------------------- #
# AB2.6 — LearnerProfileRepository.saveProfile
# --------------------------------------------------------------------------- #
def test_save_profile_persists_the_row(fake_supabase):
    """UT-2.10: a valid LearnerProfile is written and Supabase reports success."""
    fake = fake_supabase(seed={"learner_profiles": []})

    LearnerProfileRepository().save(PROFILE)

    stored = fake.store["learner_profiles"]
    assert len(stored) == 1
    assert stored[0]["learner_id"] == LEARNER_ID
    assert stored[0]["phonological_processing"] == 0.6


def test_save_profile_raises_storage_error_when_supabase_is_unreachable(monkeypatch):
    """UT-2.11: a refused write -> StorageError, so the profile is never reported saved.

    Flow 6a: the database sends a negative response and the therapist sees an error.
    """
    repo = LearnerProfileRepository()
    unreachable = Mock()
    unreachable.upsert.side_effect = ConnectionError("connection refused")
    monkeypatch.setattr(type(repo), "db", property(lambda _self: unreachable))

    with pytest.raises(StorageError):
        repo.save(PROFILE)
