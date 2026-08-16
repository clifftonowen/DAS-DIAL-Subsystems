"""INTEGRATION — POST /profiles/{learner_id}, down to the driver (UC2 "Generate Learner Profile").

Bottom-up call graph, continuing the PM3 UC2 plan's numbering past IT-2.26:

    Level 1 (repository + Supabase)
        IT-2.27  LearnerSittingRepository.latest_for_learner — newest wins, absence is None
    Level 2 (service + repositories + Supabase)
        IT-2.28  ProfilingService.generate_profile — the promotion, and its idempotence
    Level 3 (controller + everything below)
        IT-2.29  ProfileController.generateProfile — the happy path, end to end
        IT-2.30  ... the no-scores branch: NoScoresError -> 409
        IT-2.31  ... the auth guard
        IT-2.32  ... a driver failure during promotion

Real router, real service, real repositories. Only the driver underneath is faked.

WHY THIS FILE EXISTS, given IT-1.7 already posts to this endpoint. That test approaches from
UC1: upload, then promote, asserting the chain is unbroken. This one approaches from UC2 itself
and covers what that chain never reaches — the ERROR BRANCHES. Until now nothing anywhere
asserted that `NoScoresError` becomes a 409 or that the router's `except StorageError` does
anything at all. Both are one line in `routers/profiles.py`, and one of them turns out to be
dead (IT-2.32).

THE FILE NAME IS THE PM3 PLAN'S. `integration/test_uc2_generate_profile.py` is what the plan
named for IT-2.1 – IT-2.11, and it was never written because the design those IDs described
(seven derived dimensions persisted to `learner_profiles`) no longer exists. The name is reused
rather than invented so a reader tracing the plan lands somewhere; see tests/README.md for the
full superseded map.
"""
import pytest

from app.repositories.base import StorageError
from app.repositories.learner_sitting_repository import LearnerSittingRepository
from app.services.profiling_service import NoScoresError, ProfilingService

pytestmark = pytest.mark.integration

LEARNER_ID = "11111111-1111-1111-1111-111111111111"


def learner_row(learner_id=LEARNER_ID, **overrides):
    """A learner with no current marks — the state before a promotion."""
    return {
        "id": learner_id, "student_id": "Student 0142", "pseudonym": "Aisha Binti Rahman",
        "tier": "Tier 2", "on_caseload": True,
        "semester": None, "band": None, "band_group": None,
        "phonics": None, "word_reading_accuracy": None, "word_spelling": None, "writing": None,
        "writing_genre": None,
        "phonics_pct": None, "word_reading_accuracy_pct": None,
        "word_spelling_pct": None, "writing_pct": None,
        **overrides,
    }


def sitting_row(semester="2026 Sem 1", **overrides):
    return {
        "id": f"sitting-{semester}", "learner_id": LEARNER_ID, "semester": semester,
        "band": "A2", "band_group": "A", "source": "workbook",
        "phonics": 31.0, "word_reading_accuracy": 7.0, "word_spelling": 5.0,
        "writing": None, "writing_genre": None,
        "phonics_pct": 68.4, "word_reading_accuracy_pct": 41.0,
        "word_spelling_pct": 33.2, "writing_pct": None,
        **overrides,
    }


# --------------------------------------------------------------------------- #
# Level 1 — the repository over the driver
# --------------------------------------------------------------------------- #
def test_it_2_27_latest_for_learner_returns_the_newest_sitting(fake_supabase):
    """IT-2.27: 'latest' is decided by semester ordering, not insertion order.

    Semesters sort chronologically as plain TEXT ('2025 Sem 2' < '2026 Sem 1'), which is the only
    reason the column has no format constraint and still orders correctly. The rows are seeded
    out of order here so a repository that returned `rows[0]` unsorted would fail.
    """
    fake_supabase(seed={"learner_sittings": [
        sitting_row("2025 Sem 2", phonics=10.0),
        sitting_row("2026 Sem 1", phonics=31.0),
        sitting_row("2025 Sem 1", phonics=5.0),
    ]})

    latest = LearnerSittingRepository().latest_for_learner(LEARNER_ID)

    assert latest["semester"] == "2026 Sem 1"
    assert latest["phonics"] == 31.0


def test_it_2_27b_a_learner_with_no_sittings_reads_as_none(fake_supabase):
    """IT-2.27: absence is None, not an exception.

    An app-created learner has no sittings until UC1 uploads one. That is the ordinary state of
    a new learner, so the repository answers it rather than raising, and the SERVICE decides it
    is worth an error.
    """
    fake_supabase(seed={"learner_sittings": []})

    assert LearnerSittingRepository().latest_for_learner(LEARNER_ID) is None


def test_it_2_27c_sittings_belonging_to_another_learner_are_not_read(fake_supabase):
    """IT-2.27: the filter is on learner_id, so one learner cannot inherit another's marks."""
    fake_supabase(seed={"learner_sittings": [
        {**sitting_row("2026 Sem 2"), "learner_id": "22222222-2222-2222-2222-222222222222"},
        sitting_row("2026 Sem 1"),
    ]})

    latest = LearnerSittingRepository().latest_for_learner(LEARNER_ID)

    # The other learner's sitting is newer, and must lose anyway.
    assert latest["semester"] == "2026 Sem 1"


# --------------------------------------------------------------------------- #
# Level 2 — the service over both repositories
# --------------------------------------------------------------------------- #
def test_it_2_28_the_promotion_writes_the_marks_onto_the_learner(fake_supabase):
    """IT-2.28: what "generate a profile" means now — the newest sitting becomes current.

    The marks land on the `learners` row because that is what every other read uses: the radar
    chart, the cohort scatter and ActivityGenerationService all read the learner, never the
    sitting history.
    """
    fake = fake_supabase(seed={
        "learners": [learner_row()], "learner_sittings": [sitting_row()],
    })

    result = ProfilingService().generate_profile(LEARNER_ID)

    stored = fake.store["learners"][0]
    assert stored["phonics"] == 31.0
    assert stored["phonics_pct"] == 68.4
    assert stored["semester"] == "2026 Sem 1"
    # The band rides along: a mark is meaningless without the paper it was scored against, and
    # phonics is out of 30 in A2 but 46 in A3.
    assert stored["band"] == "A2"
    assert stored["band_group"] == "A"
    assert result["learner_id"] == LEARNER_ID
    assert result["source"] == "workbook"


def test_it_2_28b_the_promotion_does_not_overwrite_the_learners_identity(fake_supabase):
    """IT-2.28: only the promoted columns move.

    The sitting carries its own `id` and a `learner_id`. Writing either onto the learner would
    replace who the learner is with which sitting they sat — and `pseudonym`, `tier` and
    `on_caseload` exist nowhere in the sitting, so a full-row copy would blank them.
    """
    fake = fake_supabase(seed={
        "learners": [learner_row()], "learner_sittings": [sitting_row()],
    })

    ProfilingService().generate_profile(LEARNER_ID)

    stored = fake.store["learners"][0]
    assert stored["id"] == LEARNER_ID              # not "sitting-2026 Sem 1"
    assert stored["pseudonym"] == "Aisha Binti Rahman"
    assert stored["on_caseload"] is True
    assert stored["tier"] == "Tier 2"


def test_it_2_28c_promoting_twice_is_safe(fake_supabase):
    """IT-2.28: idempotent, because the button is pressable twice.

    Pressing Generate Profile is also how a therapist pulls through an assessment a COLLEAGUE
    just uploaded, so it has to be safe to press with nothing new to promote. A second run must
    not append a learner row or change the values.
    """
    fake = fake_supabase(seed={
        "learners": [learner_row()], "learner_sittings": [sitting_row()],
    })
    svc = ProfilingService()

    first = svc.generate_profile(LEARNER_ID)
    second = svc.generate_profile(LEARNER_ID)

    assert first == second
    assert len(fake.store["learners"]) == 1


def test_it_2_28d_a_learner_with_no_sittings_raises_no_scores(fake_supabase):
    """IT-2.28: the service, not the repository, decides absence is worth an error."""
    fake_supabase(seed={"learners": [learner_row()], "learner_sittings": []})

    with pytest.raises(NoScoresError, match=LEARNER_ID):
        ProfilingService().generate_profile(LEARNER_ID)


# --------------------------------------------------------------------------- #
# Level 3 — the controller and everything below it
# --------------------------------------------------------------------------- #
def test_it_2_29_generate_profile_returns_the_promoted_marks(client, auth_ok, fake_supabase):
    """IT-2.29: the happy path through the real router."""
    fake_supabase(seed={
        "learners": [learner_row()], "learner_sittings": [sitting_row()],
    })

    response = client.post(f"/profiles/{LEARNER_ID}")

    assert response.status_code == 200
    body = response.json()
    # `learner_id`, not `id` — the endpoint's contract answers "whose profile is this?" with the
    # learner, even though the upsert underneath keys on `id`.
    assert body["learner_id"] == LEARNER_ID
    assert body["phonics"] == 31.0
    assert body["sitting_id"] == "sitting-2026 Sem 1"


def test_it_2_30_no_scores_becomes_a_409(client, auth_ok, fake_supabase):
    """IT-2.30: NoScoresError -> 409, the status the profile page keys its upload prompt off.

    THE BRANCH NOTHING ASSERTED BEFORE THIS FILE. UT-2.62 proves the service raises; IT-1.7
    proves an upload avoids it. Neither proves the router translates it, and the UI's entire
    empty state hangs on this number.

    409 rather than 404 deliberately: the learner EXISTS and the request was well-formed, the
    resource is just not in a state that can satisfy it yet. 404 also means "no such learner",
    so collapsing them would leave the page unable to tell "upload an assessment" apart from
    "this learner is gone".
    """
    fake_supabase(seed={"learners": [learner_row()], "learner_sittings": []})

    response = client.post(f"/profiles/{LEARNER_ID}")

    assert response.status_code == 409
    assert response.status_code != 404
    # The detail is read by a human, so it has to say which learner and what to do about it.
    assert LEARNER_ID in response.json()["detail"]


def test_it_2_31_the_endpoint_is_behind_the_auth_guard(client, fake_supabase):
    """IT-2.31: no `auth_ok` override, so the dependency runs for real.

    A learner's marks are clinical data; an unauthenticated promotion would also let anyone
    rewrite a learner row.
    """
    fake_supabase(seed={
        "learners": [learner_row()], "learner_sittings": [sitting_row()],
    })

    assert client.post(f"/profiles/{LEARNER_ID}").status_code in (401, 403)


def test_it_2_32_a_driver_failure_is_not_translated(client, auth_ok, fake_supabase):
    """IT-2.32: `routers/profiles.py:32` catches StorageError, and NOTHING RAISES IT.

    THIS TEST DOCUMENTS A DEFECT rather than a behaviour. `repositories/base.StorageError` is
    raised in exactly four places (`assessment_repository`, `assessment_service` x2,
    `review_service`) and neither `LearnerRepository.save` nor
    `LearnerSittingRepository.latest_for_learner` is one of them — both call
    `.execute()` bare. So a database outage during Generate Profile escapes as the raw driver
    exception and the router's `except StorageError` clause is unreachable.

    The exception raised here escapes from the READ (`latest_for_learner`), because that is the
    first `.execute()` the request makes and `fail_on_execute` fails all of them. The write
    (`LearnerRepository.save`) is unwrapped in exactly the same way, so the finding covers both;
    naming the read here keeps the test honest about which call it actually demonstrates.

    In production FastAPI's handler still turns that into a 500, so the therapist sees the right
    status by accident; what is lost is the `detail` the clause would have supplied. The test
    asserts what the code ACTUALLY does, so that wrapping the repository later makes this test
    fail loudly and tells the next person to update it, rather than a fiction that would pass
    either way.

    Fix belongs with the repository layer, not here: wrap `.execute()` in
    `LearnerRepository.save` the way `AssessmentRepository` already does.
    """
    fake_supabase(
        seed={"learners": [learner_row()], "learner_sittings": [sitting_row()]},
        fail_on_execute=RuntimeError("connection refused"),
    )

    # Not `assert response.status_code == 500` — TestClient re-raises unhandled server
    # exceptions, which is precisely the evidence that no handler caught it.
    with pytest.raises(RuntimeError, match="connection refused"):
        client.post(f"/profiles/{LEARNER_ID}")


def test_it_2_32b_the_storage_error_clause_would_work_if_anything_raised_it(
    client, auth_ok, fake_supabase, monkeypatch,
):
    """IT-2.32: the router's 500 branch, proven correct in isolation.

    Forced by patching the service, since no repository raises StorageError today. This keeps
    the clause honest: when the repository is wrapped, the mapping it lands on is already
    tested, and the 500 is distinguishable from the 409 above.
    """
    from app.routers import profiles as router

    fake_supabase(seed={"learners": [learner_row()], "learner_sittings": [sitting_row()]})
    monkeypatch.setattr(
        router.svc, "generate_profile",
        lambda _: (_ for _ in ()).throw(StorageError("database unreachable")),
    )

    response = client.post(f"/profiles/{LEARNER_ID}")

    assert response.status_code == 500
    assert "database unreachable" in response.json()["detail"]
