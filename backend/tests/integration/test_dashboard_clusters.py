"""INTEGRATION — GET /dashboard/clusters, router down to the Supabase driver (UC2).

Bottom-up call graph, continuing the PM3 UC2 plan's numbering past IT-2.11:

    Level 1 (repository + Supabase)
        IT-2.12  LearnerScoreRepository.list_cohort — ordering and round trips
        IT-2.13  LearnerScoreRepository.list_cohort — paging past PostgREST's 1,000 cap
        IT-2.14  ClusteringRunRepository.latest_by_scope_and_tier
    Level 2 (service + both repositories + Supabase)
        IT-2.15  CohortService.get_clusters
    Level 3 (controller + everything below)
        IT-2.16  DashboardController.getCohortClusters — the happy path
        IT-2.17  ... partial data: unclustered learners, null skills, caseload links
        IT-2.18  ... empty cohort and the auth guard
        IT-2.19  ... the two clustering scopes kept distinct

Real router, real CohortService, real LearnerScoreRepository and ClusteringRunRepository.
Only the driver underneath is faked. That is the point: the reshape from learner_scores rows
to the dashboard's payload, and the paging that keeps the cohort whole, both live in the
wiring between those layers and are invisible to a unit test that mocks the repository.
"""
import pytest

from app.repositories.learner_score_repository import PAGE, LearnerScoreRepository
from app.services.cohort_service import CohortService

pytestmark = pytest.mark.integration


def score_row(student_id, cluster="B 2", cohort="Cohort 2", **overrides):
    return {
        "student_id": student_id, "learner_id": None, "band": "B4", "band_group": "B",
        "cluster_band": cluster, "cluster_cohort": cohort, "writing_genre": "narrative_writing",
        "phonics": 20.0, "word_reading_accuracy": 8.0, "word_spelling": 5.0, "writing": 12.0,
        **overrides,
    }


def run_row(tier="B", scope="band", **overrides):
    return {
        "scope": scope, "tier": tier, "features": ["phonics", "word_reading_accuracy", "word_spelling"],
        "k": 4, "best_silhouette": 0.4188,
        "silhouette_by_k": {"2": 0.3663, "3": 0.3999, "4": 0.4188},
        "n_learners": 2858, "created_at": "2026-08-05T10:00:00Z", **overrides,
    }


# ── the endpoint ──────────────────────────────────────────────────────────────
def test_returns_the_cohort_with_its_clusters(client, auth_ok, fake_supabase):
    """IT-2.16: the whole cohort and its labels over HTTP."""
    fake_supabase(seed={
        "learner_scores": [score_row("Student 0001"), score_row("Student 0002", cluster="B 3")],
        "clustering_runs": [run_row()],
    })

    body = client.get("/dashboard/clusters").json()

    assert [l["id"] for l in body["learners"]] == ["Student 0001", "Student 0002"]
    # BOTH scopes travel together so the dashboard's toggle costs no round trip.
    assert [l["cluster_band"] for l in body["learners"]] == ["B 2", "B 3"]
    assert [l["cluster_cohort"] for l in body["learners"]] == ["Cohort 2", "Cohort 2"]
    assert body["learners"][0]["phonics"] == 20.0
    assert body["unclustered"] == {"cohort": 0, "band": 0}


def test_reports_how_k_was_chosen(client, auth_ok, fake_supabase):
    """IT-2.16: the silhouette sweep reaches the client."""
    # The sweep is the evidence that k was derived rather than configured — the dashboard
    # caption reads straight off it.
    fake_supabase(seed={"learner_scores": [score_row("S1")], "clustering_runs": [run_row()]})

    run = client.get("/dashboard/clusters").json()["runs"][0]

    assert run["k"] == 4
    assert run["best_silhouette"] == pytest.approx(0.4188)
    assert run["silhouette_by_k"] == {"2": 0.3663, "3": 0.3999, "4": 0.4188}
    assert max(run["silhouette_by_k"].values()) == pytest.approx(run["best_silhouette"])


def test_one_run_per_scope_and_tier_newest_first(client, auth_ok, fake_supabase):
    """IT-2.14: only the newest run per (scope, tier) surfaces, cohort first."""
    # Ingest appends rather than overwrites, so an older fit for the same key must not
    # surface alongside the current one.
    fake_supabase(seed={
        "learner_scores": [score_row("S1")],
        "clustering_runs": [
            run_row("Cohort", scope="cohort", k=4, created_at="2026-08-06T10:00:00Z"),
            run_row("A", k=5, created_at="2026-08-05T10:00:00Z"),
            run_row("A", k=9, created_at="2026-01-01T10:00:00Z"),   # stale
            run_row("C", k=2, created_at="2026-08-05T10:00:00Z"),
        ],
    })

    runs = client.get("/dashboard/clusters").json()["runs"]

    # Cohort leads — it is the default scope, and the caption reads in this order.
    assert [(r["scope"], r["tier"], r["k"]) for r in runs] == [
        ("cohort", "Cohort", 4), ("band", "A", 5), ("band", "C", 2)]


def test_a_cohort_and_a_band_run_can_share_a_tier_name(client, auth_ok, fake_supabase):
    """IT-2.19: de-duplication keys on (scope, tier), not tier alone.

    Keying on tier alone would let a cohort model suppress the band model of the same name,
    silently dropping one of the two clusterings from the caption.
    """
    fake_supabase(seed={
        "learner_scores": [score_row("S1")],
        "clustering_runs": [
            run_row("A", scope="cohort", k=3, created_at="2026-08-06T10:00:00Z"),
            run_row("A", scope="band", k=5, created_at="2026-08-06T10:00:00Z"),
        ],
    })

    runs = client.get("/dashboard/clusters").json()["runs"]

    assert [(r["scope"], r["k"]) for r in runs] == [("cohort", 3), ("band", 5)]


def test_a_run_written_before_the_scope_column_reads_as_band(client, auth_ok, fake_supabase):
    """IT-2.19: rows predating the scope column carry the band models, per its SQL default."""
    stale = run_row("A", k=5)
    del stale["scope"]

    fake_supabase(seed={"learner_scores": [score_row("S1")], "clustering_runs": [stale]})

    assert client.get("/dashboard/clusters").json()["runs"][0]["scope"] == "band"


def test_unclustered_learners_are_counted_not_hidden(client, auth_ok, fake_supabase):
    """IT-2.17: an unlabelled learner is reported, not dropped from the payload."""
    # A learner with no band group gets no band label but still gets a cohort one, so the
    # count is per scope — a single number would be wrong for one of the two views, and the
    # dashboard's "n hidden" line would lie in whichever view it got wrong.
    fake_supabase(seed={
        "learner_scores": [
            score_row("S1"),
            score_row("S2", cluster=None, band_group=None, band=None),
        ],
        "clustering_runs": [run_row()],
    })

    body = client.get("/dashboard/clusters").json()

    assert body["unclustered"] == {"cohort": 0, "band": 1}
    assert len(body["learners"]) == 2, "an unclustered learner is still part of the cohort"
    assert body["learners"][1]["cluster_band"] is None
    assert body["learners"][1]["cluster_cohort"] == "Cohort 2"


def test_a_skill_the_learner_never_sat_stays_null(client, auth_ok, fake_supabase):
    """IT-2.17: a skill the learner never sat arrives as null, not zero."""
    # Writing is never administered to band A. Null must survive to the frontend as null:
    # coerced to 0 it would plant the learner at the bottom of the writing axis.
    fake_supabase(seed={
        "learner_scores": [score_row("S1", band_group="A", band="A3",
                                     writing=None, writing_genre=None, cluster="A 2")],
        "clustering_runs": [run_row("A")],
    })

    learner = client.get("/dashboard/clusters").json()["learners"][0]

    assert learner["writing"] is None
    assert learner["writing_genre"] is None
    assert learner["word_spelling"] == 5.0


def test_learner_id_is_carried_through_for_caseload_students(client, auth_ok, fake_supabase):
    """IT-2.17: the caseload link survives to the client."""
    # Only a learner linked to the caseload can open LearnerDetailPage; the Table gates the
    # name button on exactly this field.
    fake_supabase(seed={
        "learner_scores": [score_row("S1", learner_id="11111111-1111-1111-1111-111111111111"),
                           score_row("S2")],
        "clustering_runs": [run_row()],
    })

    learners = client.get("/dashboard/clusters").json()["learners"]

    assert learners[0]["learner_id"] == "11111111-1111-1111-1111-111111111111"
    assert learners[1]["learner_id"] is None


def test_empty_cohort_is_an_empty_payload_not_an_error(client, auth_ok, fake_supabase):
    """IT-2.18: nothing ingested yet is an empty 200, not a failure."""
    fake_supabase(seed={"learner_scores": [], "clustering_runs": []})

    response = client.get("/dashboard/clusters")

    assert response.status_code == 200
    assert response.json() == {
        "learners": [], "runs": [], "unclustered": {"cohort": 0, "band": 0}}


def test_requires_authentication(client, fake_supabase):
    """IT-2.18: the endpoint is behind current_therapist."""
    # No auth_ok fixture, so the real current_therapist dependency runs.
    fake_supabase(seed={"learner_scores": [score_row("S1")]})
    assert client.get("/dashboard/clusters").status_code in (401, 403)


# ── paging ────────────────────────────────────────────────────────────────────
def test_cohort_larger_than_one_page_comes_back_whole(client, auth_ok, fake_supabase):
    """IT-2.13: PostgREST caps a select at 1,000 rows and does NOT error when it truncates.

    The real cohort is ~5,800, so an unpaged read would quietly plot a sixth of it — a bug
    that looks like missing data. This is the test that would catch it.
    """
    total = PAGE * 2 + 137
    fake_supabase(seed={
        "learner_scores": [score_row(f"Student {i:05d}") for i in range(total)],
        "clustering_runs": [run_row()],
    })

    body = client.get("/dashboard/clusters").json()

    assert len(body["learners"]) == total
    assert len({l["id"] for l in body["learners"]}) == total, "a page was repeated"


def test_paging_reads_in_a_stable_order(fake_supabase):
    """IT-2.12: paging is ordered, so pages cannot overlap or skip."""
    # Without an explicit sort the pages may overlap or skip rows, so ordering is not
    # cosmetic here — it is what makes the loop correct.
    fake = fake_supabase(seed={
        "learner_scores": [score_row(f"Student {i:05d}") for i in reversed(range(PAGE + 10))]})

    ids = [row["student_id"] for row in LearnerScoreRepository().list_cohort()]

    assert ids == sorted(ids)


def test_a_short_first_page_makes_only_one_round_trip(fake_supabase):
    """IT-2.12: a cohort under one page costs a single round trip."""
    fake = fake_supabase(seed={"learner_scores": [score_row("S1"), score_row("S2")]})

    LearnerScoreRepository().list_cohort()

    assert len(fake.queries_on("learner_scores")) == 1


# ── service in isolation from HTTP ────────────────────────────────────────────
def test_service_maps_both_label_columns(fake_supabase):
    """IT-2.15: the service carries both scopes' labels onto the DTO, unmerged.

    Merging them here — picking one to call `cluster` — would decide the dashboard's default
    scope in the service layer, and the toggle could then only reach the other by refetching.
    """
    fake_supabase(seed={
        "learner_scores": [score_row("S1", cluster="C 1", cohort="Cohort 3")],
        "clustering_runs": [],
    })

    result = CohortService().get_clusters()

    assert result.learners[0].id == "S1"
    assert result.learners[0].cluster_band == "C 1"
    assert result.learners[0].cluster_cohort == "Cohort 3"
