"""INTEGRATION — GET /learners/{id}/overview and GET /learners, down to the driver (UC2).

Bottom-up call graph, continuing the PM3 UC2 plan's numbering past IT-2.19:

    Level 1 (repository + Supabase)
        IT-2.20  LearnerRepository.list_page — paging, search and the caseload filter
        IT-2.21  LearnerRepository.count — a count, not a truncated row fetch
    Level 2 (service + repositories + Supabase)
        IT-2.22  LearnerOverviewService.get_overview — learner row + sitting history
    Level 3 (controller + everything below)
        IT-2.23  LearnerController.getLearnerOverview — the happy path
        IT-2.24  ... partial data: no history, no marks, neither
        IT-2.25  ... the auth guard and the unknown learner
        IT-2.26  LearnerController.listLearners — the page/search/count contract

Real router, real services, real repositories. Only the driver underneath is faked.

WHAT CHANGED HERE. This file first tested a join across `learners` and `learner_scores`, then
a join to `learner_profiles`. Both are gone: the marks are columns on the learner row, and the
seven derived dimensions were mock scaffolding. What is left to prove is that the page contract
holds at cohort scale, and that a learner's SCORE HISTORY reaches the client in the order the
chart needs it.
"""
import pytest

from app.repositories.learner_repository import PAGE, LearnerRepository
from app.services.learner_overview_service import LearnerOverviewService

pytestmark = pytest.mark.integration

CASELOAD_ID = "11111111-1111-1111-1111-111111111111"
COHORT_ID = "22222222-2222-2222-2222-222222222222"


def caseload_row(learner_id=CASELOAD_ID, **overrides):
    """A therapist's learner who is also in the workbook — marks AND a name."""
    return {
        "id": learner_id, "student_id": "Student 0142", "pseudonym": "Aisha Binti Rahman",
        "tier": "Tier 2", "on_caseload": True,
        "semester": "2026 Sem 1", "band": "A2", "band_group": "A",
        "school_level": "Primary", "age": 9,
        "cluster_band": "A 3", "cluster_cohort": "Cohort 2",
        "phonics": 31.0, "word_reading_accuracy": 7.0, "word_spelling": 5.0, "writing": None,
        "fluency_mark": 14.0,
        "phonics_pct": 68.4, "word_reading_accuracy_pct": 41.0,
        "word_spelling_pct": 33.2, "writing_pct": None,
        **overrides,
    }


def cohort_row(learner_id=COHORT_ID, student_id="Student 0001", **overrides):
    """Anonymised research data: marks, no name, no caseload."""
    return caseload_row(
        learner_id, student_id=student_id, pseudonym="", tier="", on_caseload=False, **overrides
    )


def sitting_row(learner_id=CASELOAD_ID, semester="2026 Sem 1", **overrides):
    """One row of history. The ingest writes these; UC1's upload appends one with source='upload'."""
    return {
        "id": f"s-{learner_id}-{semester}", "learner_id": learner_id, "semester": semester,
        "band": "A2", "band_group": "A", "source": "workbook",
        "phonics": 31.0, "word_reading_accuracy": 7.0, "word_spelling": 5.0, "writing": None,
        "phonics_pct": 68.4, "word_reading_accuracy_pct": 41.0,
        "word_spelling_pct": 33.2, "writing_pct": None,
        **overrides,
    }


# ── the overview endpoint ─────────────────────────────────────────────────────
def test_returns_identity_marks_and_history_together(client, auth_ok, fake_supabase):
    """IT-2.23: one call, everything the detail page renders."""
    fake_supabase(seed={
        "learners": [caseload_row()],
        "learner_sittings": [sitting_row(semester="2025 Sem 1"), sitting_row()],
    })

    body = client.get(f"/learners/{CASELOAD_ID}/overview").json()

    assert body["pseudonym"] == "Aisha Binti Rahman"
    assert body["on_caseload"] is True
    assert body["band"] == "A2"
    assert body["student_id"] == "Student 0142"
    assert body["cluster_cohort"] == "Cohort 2"
    assert [p["semester"] for p in body["history"]] == ["2025 Sem 1", "2026 Sem 1"]


def test_the_marks_come_off_the_learner_row_itself(client, auth_ok, fake_supabase):
    """IT-2.22: no join, and no chance of picking up someone else's marks.

    Two learners with different marks. Before the merge this needed a nullable FK and could
    return the wrong row from a mis-filtered query; now the marks cannot be anyone else's,
    because they are columns on the row the id already selected.
    """
    fake_supabase(seed={
        "learners": [
            caseload_row(phonics=31.0, phonics_pct=68.4),
            cohort_row(phonics=5.0, phonics_pct=10.0),
        ],
        "learner_sittings": [],
    })

    body = client.get(f"/learners/{CASELOAD_ID}/overview").json()

    assert next(m for m in body["metrics"] if m["key"] == "phonics")["raw"] == 31.0


def test_history_comes_back_oldest_first_however_it_was_stored(client, auth_ok, fake_supabase):
    """IT-2.22: the chart plots left to right, so the series must arrive in that order.

    Sittings land in whatever order the ingest batched them, and UC1 appends later ones at any
    time. Sorting in the repository rather than the browser keeps one rule in one place.
    """
    fake_supabase(seed={
        "learners": [caseload_row()],
        "learner_sittings": [
            sitting_row(semester="2026 Sem 1"),
            sitting_row(semester="2022 Sem 1"),
            sitting_row(semester="2024 Sem 2"),
        ],
    })

    body = client.get(f"/learners/{CASELOAD_ID}/overview").json()

    assert [p["semester"] for p in body["history"]] == [
        "2022 Sem 1", "2024 Sem 2", "2026 Sem 1"]


def test_an_unassessed_paper_reaches_the_client_as_unassessed(client, auth_ok, fake_supabase):
    """IT-2.24: writing is absent for band A, and arrives saying so.

    The radar chart drops the axis on this flag. Were it coerced to 0/assessed anywhere down
    the stack, the chart would draw a band A learner at the bottom of a writing paper that is
    never administered to band A at all.
    """
    fake_supabase(seed={"learners": [caseload_row()], "learner_sittings": [sitting_row()]})

    metrics = {
        m["key"]: m
        for m in client.get(f"/learners/{CASELOAD_ID}/overview").json()["metrics"]
    }

    assert metrics["writing"]["assessed"] is False
    assert metrics["writing"]["raw"] is None
    assert metrics["phonics"]["assessed"] is True
    assert metrics["phonics"]["percentile"] == 68.4
    assert metrics["phonics"]["max"] == 46.0, "the rubric ceiling is served, not kept in the UI"


def test_a_cohort_learner_gets_the_same_payload(client, auth_ok, fake_supabase):
    """IT-2.24: the research cohort is not a second-class learner any more.

    They have the same four marks, so their page offers the same actions. `on_caseload` marks
    them for the badge and nothing else — it used to gate the whole page.
    """
    fake_supabase(seed={
        "learners": [cohort_row()],
        "learner_sittings": [sitting_row(learner_id=COHORT_ID)],
    })

    body = client.get(f"/learners/{COHORT_ID}/overview").json()

    assert body["on_caseload"] is False
    assert body["pseudonym"] == ""
    assert len([m for m in body["metrics"] if m["assessed"]]) == 3, "marks still show"
    assert len(body["history"]) == 1, "and so does their history"


def test_a_learner_with_no_marks_still_loads(client, auth_ok, fake_supabase):
    """IT-2.24: an app-created learner has no workbook row behind them."""
    bare = {"id": CASELOAD_ID, "pseudonym": "New Learner", "on_caseload": True,
            "student_id": None, "tier": "Tier 1"}
    fake_supabase(seed={"learners": [bare], "learner_sittings": []})

    body = client.get(f"/learners/{CASELOAD_ID}/overview").json()

    assert body["student_id"] is None
    assert all(not m["assessed"] for m in body["metrics"])
    assert len(body["metrics"]) == 4, "the chart names what it omitted, so all four travel"


def test_an_unknown_learner_is_a_404(client, auth_ok, fake_supabase):
    """IT-2.25: the one absence that is an error."""
    fake_supabase(seed={"learners": [], "learner_sittings": []})

    assert client.get("/learners/does-not-exist/overview").status_code == 404


def test_overview_requires_authentication(client, fake_supabase):
    """IT-2.25: the endpoint is behind current_therapist."""
    fake_supabase(seed={"learners": [caseload_row()]})
    assert client.get(f"/learners/{CASELOAD_ID}/overview").status_code in (401, 403)


# ── the list endpoint ─────────────────────────────────────────────────────────
def test_list_returns_one_page_and_the_total(client, auth_ok, fake_supabase):
    """IT-2.26: the pager's contract.

    A bare array was viable when `learners` held ten rows. It holds thousands now, and
    PostgREST truncates at 1,000 WITHOUT erroring — so the endpoint pages, and `total` is what
    tells the client there is more.
    """
    fake_supabase(seed={"learners": [
        cohort_row(f"uuid-{i}", f"Student {i:04d}") for i in range(70)]})

    body = client.get("/learners?per_page=24&caseload=false").json()

    assert len(body["items"]) == 24
    assert body["total"] == 70
    assert body["page"] == 1 and body["per_page"] == 24


def test_list_defaults_to_the_caseload(client, auth_ok, fake_supabase):
    """IT-2.26: the Learners tab opens on the therapist's own learners.

    Without the default, it would open on thousands of anonymised research rows and the ten
    learners the therapist actually works with would be somewhere on page 200.
    """
    fake_supabase(seed={"learners": [
        caseload_row(),
        *(cohort_row(f"uuid-{i}", f"Student {i:04d}") for i in range(30)),
    ]})

    body = client.get("/learners").json()

    assert body["total"] == 1
    assert body["items"][0]["pseudonym"] == "Aisha Binti Rahman"


def test_list_search_reaches_both_kinds_of_learner(client, auth_ok, fake_supabase):
    """IT-2.26: search spans pseudonym and student_id, because neither alone covers both."""
    fake_supabase(seed={"learners": [caseload_row(), cohort_row("uuid-c", "Student 0999")]})

    by_name = client.get("/learners?q=aisha&caseload=false").json()
    by_id = client.get("/learners?q=0999&caseload=false").json()

    assert [i["pseudonym"] for i in by_name["items"]] == ["Aisha Binti Rahman"]
    assert [i["student_id"] for i in by_id["items"]] == ["Student 0999"]


def test_list_per_page_is_clamped(client, auth_ok, fake_supabase):
    """IT-2.26: per_page arrives from the query string and is not trusted.

    Unbounded, it would let a caller pull the whole table in one request — the exact read the
    endpoint exists to prevent.
    """
    fake_supabase(seed={"learners": [cohort_row(f"uuid-{i}", f"S{i}") for i in range(10)]})

    assert client.get("/learners?per_page=100000").status_code == 422


def test_list_requires_authentication(client, fake_supabase):
    fake_supabase(seed={"learners": [caseload_row()]})
    assert client.get("/learners").status_code in (401, 403)


# ── repository, past the row cap ──────────────────────────────────────────────
def test_count_sees_past_the_postgrest_cap(fake_supabase):
    """IT-2.21: the dashboard's Total Learners.

    `len(select("*"))` would report 1,000 forever once the cohort landed in this table, and
    move the whole table to do it.
    """
    total = PAGE + 42
    fake_supabase(seed={"learners": [
        cohort_row(f"uuid-{i}", f"Student {i:05d}") for i in range(total)]})

    assert LearnerRepository().count() == total


def test_paging_a_search_stays_consistent(fake_supabase):
    """IT-2.20: the total respects the filter, so the pager cannot offer empty pages."""
    fake_supabase(seed={
        "learners": [
            *(cohort_row(f"uuid-a{i}", f"Student A{i:04d}") for i in range(30)),
            *(cohort_row(f"uuid-b{i}", f"Student B{i:04d}") for i in range(5)),
        ],
    })

    rows, total = LearnerRepository().list_page(
        limit=10, offset=0, query="Student B", caseload_only=False)

    assert total == 5
    assert len(rows) == 5


# ── service in isolation from HTTP ────────────────────────────────────────────
def test_service_composes_without_the_router(fake_supabase):
    """IT-2.22: the composition is the service's, not the router's."""
    fake_supabase(seed={
        "learners": [caseload_row()],
        "learner_sittings": [sitting_row()],
    })

    out = LearnerOverviewService().get_overview(CASELOAD_ID)

    assert out.student_id == "Student 0142"
    assert out.band_group == "A", "the population the percentiles are ranked against"
    assert out.on_caseload is True
    assert out.history[0].phonics_pct == 68.4
