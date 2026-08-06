"""UNIT — LearnerRepository in isolation.

One "activation bar": a single repository method, with the database driver replaced by the
in-memory FakeSupabase. No service, no router, no network.

`learners` holds BOTH the therapist's caseload and the ~5,783-row anonymised DAS research
cohort (infra/migrations/2026-08-07_merge_learner_scores.sql), and almost every test here
exists because of that scale:

  * PostgREST caps a select at 1,000 rows and TRUNCATES WITHOUT ERRORING, so an unpaged read
    returns a fraction of the table and looks perfectly healthy doing it
  * a count must be a count(), not len(rows), for the same reason
  * the ingest upserts on `student_id`, not the uuid primary key, and must not touch the
    columns that carry caseload identity
"""
import pytest

from app.repositories.learner_repository import PAGE, LearnerRepository

pytestmark = pytest.mark.unit


def caseload(learner_id, pseudonym, **overrides):
    return {"id": learner_id, "student_id": None, "pseudonym": pseudonym, "tier": "Tier 2",
            "on_caseload": True, "band": "A2", "band_group": "A", **overrides}


def cohort(learner_id, student_id, **overrides):
    return {"id": learner_id, "student_id": student_id, "pseudonym": "", "tier": "",
            "on_caseload": False, "band": "B4", "band_group": "B", **overrides}


# ── find ──────────────────────────────────────────────────────────────────────
def test_find_by_id_returns_matching_row(fake_supabase):
    fake_supabase(seed={"learners": [caseload("l1", "Ada"), caseload("l2", "Bo")]})

    assert LearnerRepository().find_by_id("l1")["pseudonym"] == "Ada"


def test_find_by_id_returns_none_when_absent(fake_supabase):
    fake_supabase(seed={"learners": []})

    assert LearnerRepository().find_by_id("missing") is None


def test_find_by_student_id_reaches_the_cohort(fake_supabase):
    fake_supabase(seed={"learners": [caseload("l1", "Ada"), cohort("l2", "Student 0142")]})

    assert LearnerRepository().find_by_student_id("Student 0142")["id"] == "l2"


# ── count ─────────────────────────────────────────────────────────────────────
def test_count_is_a_count_not_a_row_fetch(fake_supabase):
    """The dashboard's Total Learners.

    `len(list_all())` — what this replaced — both moved the whole table and, past PostgREST's
    1,000-row cap, reported the cap rather than the truth. A table of 5,783 would have read
    "1,000 learners enrolled" indefinitely, with nothing anywhere saying why.
    """
    total = PAGE + 250
    fake_supabase(seed={"learners": [cohort(f"id-{i}", f"Student {i:05d}") for i in range(total)]})

    assert LearnerRepository().count() == total


def test_count_can_be_scoped_to_the_caseload(fake_supabase):
    fake_supabase(seed={"learners": [
        caseload("l1", "Ada"), caseload("l2", "Bo"), cohort("l3", "Student 0001")]})
    repo = LearnerRepository()

    assert repo.count() == 3
    assert repo.count(caseload_only=True) == 2


# ── list_page ─────────────────────────────────────────────────────────────────
def test_list_page_returns_a_page_and_the_full_total(fake_supabase):
    """The pager needs both: 24 rows to render and 5,783 to say "1-24 of"."""
    fake_supabase(seed={"learners": [cohort(f"id-{i:04d}", f"Student {i:04d}") for i in range(70)]})

    rows, total = LearnerRepository().list_page(limit=24, offset=0, caseload_only=False)

    assert len(rows) == 24
    assert total == 70, "the total counts the filtered set, not the page"


def test_list_page_offsets_without_overlapping(fake_supabase):
    fake_supabase(seed={"learners": [cohort(f"id-{i:04d}", f"Student {i:04d}") for i in range(70)]})
    repo = LearnerRepository()

    first, _ = repo.list_page(limit=24, offset=0, caseload_only=False)
    second, _ = repo.list_page(limit=24, offset=24, caseload_only=False)

    assert not {r["id"] for r in first} & {r["id"] for r in second}


def test_caseload_learners_lead_the_list(fake_supabase):
    """The therapist's own learners sort first, whatever the cohort is called.

    Cohort ids sort before every pseudonym alphabetically, so without the on_caseload sort key
    the caseload would be buried on the last page of thousands.
    """
    fake_supabase(seed={"learners": [
        cohort("c1", "Student 0001"),
        caseload("l1", "Zara"),
        cohort("c2", "Student 0002"),
    ]})

    rows, _ = LearnerRepository().list_page(limit=10, offset=0, caseload_only=False)

    assert rows[0]["pseudonym"] == "Zara"


def test_caseload_filter_excludes_the_cohort(fake_supabase):
    fake_supabase(seed={"learners": [
        caseload("l1", "Ada"), cohort("c1", "Student 0001"), cohort("c2", "Student 0002")]})

    rows, total = LearnerRepository().list_page(limit=10, offset=0, caseload_only=True)

    assert [r["id"] for r in rows] == ["l1"]
    assert total == 1, "the total must respect the filter, or the pager offers empty pages"


# ── search ────────────────────────────────────────────────────────────────────
def test_search_matches_a_caseload_pseudonym(fake_supabase):
    fake_supabase(seed={"learners": [caseload("l1", "Aisha Binti Rahman"), caseload("l2", "Bo")]})

    rows, total = LearnerRepository().list_page(limit=10, offset=0, query="aisha")

    assert [r["id"] for r in rows] == ["l1"]
    assert total == 1


def test_search_matches_an_anonymised_student_id(fake_supabase):
    """A cohort learner has no pseudonym, so their workbook id is the only thing to search on.

    This is why the search spans three columns rather than one — neither `pseudonym` nor
    `student_id` alone can find both kinds of learner.
    """
    fake_supabase(seed={"learners": [
        cohort("c1", "Student 0142"), cohort("c2", "Student 0999")]})

    rows, _ = LearnerRepository().list_page(limit=10, offset=0, query="0142", caseload_only=False)

    assert [r["student_id"] for r in rows] == ["Student 0142"]


def test_search_matches_a_band(fake_supabase):
    fake_supabase(seed={"learners": [
        caseload("l1", "Ada", band="A2"), caseload("l2", "Bo", band="C7")]})

    rows, _ = LearnerRepository().list_page(limit=10, offset=0, query="C7")

    assert [r["id"] for r in rows] == ["l2"]


def test_search_is_case_insensitive(fake_supabase):
    fake_supabase(seed={"learners": [caseload("l1", "Aisha Binti Rahman")]})

    rows, _ = LearnerRepository().list_page(limit=10, offset=0, query="AISHA")

    assert len(rows) == 1


def test_search_punctuation_cannot_break_the_filter(fake_supabase):
    """`,` and `.` are or_() syntax, so user-typed text carrying them must be neutralised.

    Unescaped, a query like "Ada,x.eq.1" would be parsed as extra filter terms — this is the
    injection boundary for the search box, and the repository strips rather than trusts.
    """
    fake_supabase(seed={"learners": [caseload("l1", "Ada"), caseload("l2", "Bo")]})

    rows, _ = LearnerRepository().list_page(limit=10, offset=0, query="Ada,on_caseload.eq.false")

    assert rows == [], "the whole string is one search term, and nobody is named that"


def test_an_empty_search_does_not_filter(fake_supabase):
    fake_supabase(seed={"learners": [caseload("l1", "Ada"), caseload("l2", "Bo")]})

    rows, _ = LearnerRepository().list_page(limit=10, offset=0, query="   ")

    assert len(rows) == 2


# ── list_cohort ───────────────────────────────────────────────────────────────
def test_list_cohort_pages_past_the_postgrest_cap(fake_supabase):
    """PostgREST caps a select at 1,000 rows and does NOT error when it truncates.

    The scatter would quietly plot a sixth of the cohort — a bug that looks like missing data.
    """
    total = PAGE * 2 + 137
    fake_supabase(seed={"learners": [cohort(f"id-{i:05d}", f"Student {i:05d}") for i in range(total)]})

    rows = LearnerRepository().list_cohort()

    assert len(rows) == total
    assert len({r["id"] for r in rows}) == total, "a page was repeated"


def test_list_cohort_includes_caseload_learners(fake_supabase):
    """The scatter plots everyone. A caseload learner with marks is a point like any other."""
    fake_supabase(seed={"learners": [caseload("l1", "Ada"), cohort("c1", "Student 0001")]})

    assert len(LearnerRepository().list_cohort()) == 2


# ── upsert ────────────────────────────────────────────────────────────────────
def test_upsert_conflicts_on_student_id_not_the_uuid(fake_supabase):
    """The workbook has never heard of a uuid.

    Conflicting on the primary key would insert a fresh row every run, and the cohort would
    double in size on each re-ingest instead of being updated in place.
    """
    fake = fake_supabase(seed={"learners": [cohort("c1", "Student 0142", phonics=20.0)]})

    LearnerRepository().upsert_many([{"student_id": "Student 0142", "phonics": 31.0}])

    rows = fake.store["learners"]
    assert len(rows) == 1, "a second row means the upsert conflicted on the wrong column"
    assert rows[0]["phonics"] == 31.0
    assert rows[0]["id"] == "c1", "the uuid is stable, so profiles keep pointing at it"


def test_a_reingest_leaves_caseload_identity_alone(fake_supabase):
    """THE ONE THAT PROTECTS REAL LEARNERS.

    A learner can be both on the caseload and in the workbook. An upsert updates the columns
    its payload carries and leaves the rest, so as long as the ingest never sends `pseudonym`,
    `tier` or `on_caseload`, a re-ingest refreshes their marks without anonymising them. If
    those names ever creep into ingest_dial_data.STORED, this is what goes red.
    """
    fake = fake_supabase(seed={"learners": [
        caseload("l1", "Aisha Binti Rahman", student_id="Student 0142", phonics=20.0)]})

    LearnerRepository().upsert_many([{"student_id": "Student 0142", "phonics": 31.0}])

    row = fake.store["learners"][0]
    assert row["phonics"] == 31.0, "the marks did refresh"
    assert row["pseudonym"] == "Aisha Binti Rahman"
    assert row["on_caseload"] is True
    assert row["tier"] == "Tier 2"


def test_upsert_batches_large_payloads(fake_supabase):
    """One 5,783-row request exceeds Supabase's payload limit."""
    fake = fake_supabase(seed={"learners": []})
    rows = [{"student_id": f"Student {i:05d}", "phonics": 1.0} for i in range(1200)]

    LearnerRepository().upsert_many(rows, batch=500)

    assert len(fake.store["learners"]) == 1200
    assert len(fake.queries_on("learners")) == 3, "1200 rows in batches of 500"


def test_there_is_no_delete_all(fake_supabase):
    """`learner_sittings` and `assessment_records` cascade from this table.

    The cohort ingest used to clear its table before loading. On the merged table that would
    delete caseload learners and take their generated profiles with them, so the method — and
    the --replace flag that called it — are deliberately gone.
    """
    assert not hasattr(LearnerRepository, "delete_all")
