"""INTEGRATION — UC2 Generate Learner Profile, bottom-up call graph.

The call graph is read off the UC2 sequence diagram: each lifeline is a node, each
synchronous message an edge, and a lifeline's call depth is its level. Bottom-up means
starting at the rightmost (leaf) lifelines and adding one level per step until the
controller is reached. Nothing between the layers is mocked — only the Supabase driver.

    Level 1 (repository + Supabase)
        IT-2.1, IT-2.2   LearnerProfileRepository.saveProfile
        IT-2.3, IT-2.4   AssessmentRepository.findByLearner
    Level 2 (algorithm + repository + Supabase)
        IT-2.5, IT-2.6   ProfilingAlgorithm.analyse + saveProfile
    Level 3 (service + everything below)
        IT-2.7, IT-2.8, IT-2.9    ProfilingService.generateProfile
    Level 4 (controller + everything below)
        IT-2.10, IT-2.11          ProfileController.generateProfile

The "Supabase unreachable" cases (IT-2.2, IT-2.4) cannot be expressed by seeding
FakeSupabase — an empty table is a successful read of nothing, not a failure. They install a
client whose call raises instead, which is what an unreachable PostgREST actually looks like
from inside a repository.
"""
import pytest
from unittest.mock import Mock

from app.agents.profiling_algorithm import DIMENSIONS, NEUTRAL, NoPatternError, ProfilingAlgorithm
from app.repositories.assessment_repository import AssessmentRepository
from app.repositories.base import StorageError
from app.repositories.learner_profile_repository import LearnerProfileRepository
from app.routers import profiles as profiles_router  # noqa: F401  (registers the route)
from app.services.profiling_service import (
    EmptyDataError, ProfileGenerationError, ProfilingService)

pytestmark = pytest.mark.integration

LEARNER_ID = "11111111-1111-4111-8111-111111111111"


def record(tasks, date="2026-07-01"):
    return {"learner_id": LEARNER_ID, "assessment_date": date, "task_results": tasks}


SCORABLE = record({"Phoneme Segmentation": {"score": 6, "max_score": 10}})
# Routes to no dimension: "Handwriting Neatness" is motor skill, deliberately excluded from
# the spelling keywords. Evidences nothing, so analyse() raises NoPatternError.
UNSCORABLE = record({"Handwriting Neatness": {"score": 3, "max_score": 10}})

PROFILE = {"learner_id": LEARNER_ID, **{d: NEUTRAL for d in DIMENSIONS}}


def unreachable(repo, method):
    """Replace a repository's Supabase handle with one that fails on `method`."""
    client = Mock()
    getattr(client, method).side_effect = ConnectionError("connection refused")
    return property(lambda _self: client)


# --------------------------------------------------------------------------- #
# Level 1 — repository + Supabase
# --------------------------------------------------------------------------- #
def test_save_profile_reaches_the_database(fake_supabase):
    """IT-2.1: saveProfile + Supabase -> the LearnerProfile row exists afterwards."""
    fake = fake_supabase(seed={"learner_profiles": []})

    LearnerProfileRepository().save(PROFILE)

    assert fake.store["learner_profiles"][0]["learner_id"] == LEARNER_ID
    assert fake.queries_on("learner_profiles") == [("learner_profiles", "upsert")]


def test_save_profile_surfaces_a_storage_error(monkeypatch):
    """IT-2.2: Supabase unreachable -> StorageError and no row written."""
    repo = LearnerProfileRepository()
    monkeypatch.setattr(type(repo), "db", unreachable(repo, "upsert"))

    with pytest.raises(StorageError):
        repo.save(PROFILE)


def test_find_by_learner_reaches_the_database(fake_supabase):
    """IT-2.3: findByLearner + Supabase -> the learner's AssessmentRecords."""
    fake_supabase(seed={"assessment_records": [SCORABLE]})

    rows = AssessmentRepository().find_by_learner(LEARNER_ID)

    assert [r["learner_id"] for r in rows] == [LEARNER_ID]


def test_find_by_learner_surfaces_a_storage_error(monkeypatch):
    """IT-2.4: Supabase unreachable -> StorageError rather than an empty list.

    Returning [] here would be indistinguishable from an un-assessed learner, and the
    service would raise EmptyDataError — telling the therapist to upload data they
    already have.
    """
    repo = AssessmentRepository()
    monkeypatch.setattr(type(repo), "db", unreachable(repo, "select"))

    with pytest.raises(StorageError):
        repo.find_by_learner(LEARNER_ID)


# --------------------------------------------------------------------------- #
# Level 2 — algorithm + repository + Supabase
# --------------------------------------------------------------------------- #
def test_analyse_output_is_storable_as_written(fake_supabase):
    """IT-2.5: analyse() + saveProfile + Supabase — the metrics land in the table.

    The contract this protects: analyse() must return EXACTLY the seven learner_profiles
    columns. An extra key is a "column does not exist" error from Supabase, which only
    shows up once these two are wired together.
    """
    fake = fake_supabase(seed={"learner_profiles": []})

    metrics = ProfilingAlgorithm().analyse([SCORABLE])
    LearnerProfileRepository().save({"learner_id": LEARNER_ID, **metrics})

    stored = fake.store["learner_profiles"][0]
    assert set(stored) == set(DIMENSIONS) | {"learner_id"}
    assert stored["phonological_processing"] == 0.6


def test_no_patterns_means_nothing_reaches_the_database(fake_supabase):
    """IT-2.6: analyse() raises NoPatternError, so saveProfile is never called."""
    fake = fake_supabase(seed={"learner_profiles": []})

    with pytest.raises(NoPatternError):
        metrics = ProfilingAlgorithm().analyse([UNSCORABLE])
        LearnerProfileRepository().save({"learner_id": LEARNER_ID, **metrics})

    assert fake.store["learner_profiles"] == []


# --------------------------------------------------------------------------- #
# Level 3 — service + algorithm + both repositories + Supabase
# --------------------------------------------------------------------------- #
def test_service_generates_and_stores_end_to_end(fake_supabase):
    """IT-2.7: the whole service path, real collaborators, only the driver faked."""
    fake = fake_supabase(seed={
        "assessment_records": [SCORABLE],
        "learner_profiles": [],
    })

    result = ProfilingService().generate_profile(LEARNER_ID)

    assert result["phonological_processing"] == 0.6
    assert fake.store["learner_profiles"][0]["learner_id"] == LEARNER_ID
    # Both edges of the sequence diagram were taken, in order.
    assert [q[0] for q in fake.queries] == ["assessment_records", "learner_profiles"]


def test_service_aborts_when_the_learner_has_no_records(fake_supabase):
    """IT-2.8: no records -> EmptyDataError, and learner_profiles is never touched."""
    fake = fake_supabase(seed={"assessment_records": [], "learner_profiles": []})

    with pytest.raises(EmptyDataError):
        ProfilingService().generate_profile(LEARNER_ID)

    assert fake.store["learner_profiles"] == []
    assert fake.queries_on("learner_profiles") == []


def test_service_aborts_when_the_records_evidence_nothing(fake_supabase):
    """IT-2.9: records exist but yield no patterns -> ProfileGenerationError, nothing saved."""
    fake = fake_supabase(seed={"assessment_records": [UNSCORABLE], "learner_profiles": []})

    with pytest.raises(ProfileGenerationError):
        ProfilingService().generate_profile(LEARNER_ID)

    assert fake.store["learner_profiles"] == []


def test_service_reads_records_newest_first(fake_supabase):
    """IT-2.7 (boundary): the newest sitting wins for a dimension it evidences.

    find_by_learner orders by assessment_date desc and analyse() takes the first record
    carrying evidence, so a learner's current ability is not diluted by older sittings.
    Only visible with the real repository ordering underneath the real algorithm.
    """
    fake_supabase(seed={
        "assessment_records": [
            record({"Phoneme Segmentation": {"score": 1, "max_score": 10}}, "2025-01-01"),
            record({"Phoneme Segmentation": {"score": 9, "max_score": 10}}, "2026-07-01"),
        ],
        "learner_profiles": [],
    })

    result = ProfilingService().generate_profile(LEARNER_ID)

    assert result["phonological_processing"] == 0.9


# --------------------------------------------------------------------------- #
# Level 4 — controller + service + algorithm + repositories + Supabase
# --------------------------------------------------------------------------- #
def test_controller_generates_a_profile_over_http(client, auth_ok, fake_supabase):
    """IT-2.10: POST /profiles/{id} -> 200, and the row exists in the database."""
    fake = fake_supabase(seed={
        "assessment_records": [SCORABLE],
        "learner_profiles": [],
    })

    resp = client.post(f"/profiles/{LEARNER_ID}")

    assert resp.status_code == 200
    assert resp.json()["phonological_processing"] == 0.6
    assert len(fake.store["learner_profiles"]) == 1


def test_controller_returns_404_when_the_learner_has_no_records(
        client, auth_ok, fake_supabase):
    """IT-2.11: EmptyDataError travels the full stack and arrives as a 404 with a reason."""
    fake = fake_supabase(seed={"assessment_records": [], "learner_profiles": []})

    resp = client.post(f"/profiles/{LEARNER_ID}")

    assert resp.status_code == 404
    assert "No assessment records" in resp.json()["detail"]
    assert fake.store["learner_profiles"] == []


def test_controller_returns_422_when_the_records_evidence_nothing(
        client, auth_ok, fake_supabase):
    """IT-2.11 (boundary): the no-patterns branch is a 422, distinct from the 404 above.

    Both mean "no profile", but the therapist's next action differs — upload an assessment
    versus look at the records they already uploaded.
    """
    fake_supabase(seed={"assessment_records": [UNSCORABLE], "learner_profiles": []})

    assert client.post(f"/profiles/{LEARNER_ID}").status_code == 422
