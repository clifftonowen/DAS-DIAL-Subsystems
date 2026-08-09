"""UNIT — the DIAL workbook reader (Subsystem 2, UC2 cohort ingestion).

    AB2.9   dial_workbook.load_latest_per_student()  UT-2.21, UT-2.22
    AB2.10  dial_workbook._collapse_writing()        UT-2.23, UT-2.24
    AB2.11  dial_workbook._band_group()              UT-2.25
    AB2.12  dial_workbook.coverage() + feature sets  UT-2.26
    AB2.18  dial_workbook.percentiles()              UT-2.46, UT-2.47
    AB2.26  dial_workbook.latest_per_semester()      UT-2.71, UT-2.72

Extends the PM3 UC2 test plan (see test_profiling_algorithm_cluster.py for why).

Every case builds a tiny in-memory DataFrame rather than reading the real 3.7 MB workbook,
so these run in milliseconds and are safe in CI where that file is not present (it is
gitignored source material).

The reductions under test all encode a measured fact about the real data — the writing
genres being mutually exclusive, students recurring across semesters — and each test names
the fact it protects.
"""
import pytest

pd = pytest.importorskip(
    "pandas",
    reason="pandas is in requirements-analysis.txt (notebook + ingest only), not the API's "
           "runtime deps — the workbook is never read by the running service.",
)

from app.ingestion.dial_workbook import (  # noqa: E402  (must follow the importorskip)
    CLUSTER_FEATURES,
    PERCENTILE_COLUMNS,
    PLOT_FEATURES,
    UNBANDED,
    _band_group,
    _collapse_writing,
    coverage,
    latest_per_semester,
    latest_per_student,
    percentiles,
    writing_genre_audit,
)

pytestmark = pytest.mark.unit


def frame(rows):
    """A DataFrame with every column load_workbook() produces, defaults filled in."""
    base = {
        "student_id": "S1", "semester": "2024 Sem 1", "band": "B4", "school_level": "Primary",
        "age": 10, "phonics": 20.0, "word_reading_accuracy": 8.0, "word_spelling": 5.0,
        "narrative_writing": 0.0, "exposition_writing": 0.0, "persuasive_writing": 0.0,
        "fluency_mark": 16.0, "_sitting_date": pd.NaT,
    }
    df = pd.DataFrame([{**base, **r} for r in rows])
    df["writing"], df["writing_genre"] = _collapse_writing(df)
    df["band_group"] = _band_group(df["band"])
    return df


# ── latest_per_student ────────────────────────────────────────────────────────
def test_keeps_only_the_most_recent_semester_per_student():
    """UT-2.21: sittings reduce to one row per student — the latest."""
    df = frame([
        {"student_id": "S1", "semester": "2022 Sem 1", "phonics": 1.0},
        {"student_id": "S1", "semester": "2026 Sem 1", "phonics": 9.0},
        {"student_id": "S1", "semester": "2024 Sem 2", "phonics": 5.0},
        {"student_id": "S2", "semester": "2023 Sem 1", "phonics": 3.0},
    ])
    out = latest_per_student(df)

    assert len(out) == 2
    assert out.set_index("student_id").loc["S1", "phonics"] == 9.0


def test_semester_strings_order_chronologically_across_years():
    """UT-2.21: the semester string sorts chronologically as plain text."""
    # The whole reduction rests on "2022 Sem 2" < "2023 Sem 1" as plain text. Were that
    # false, students would be pinned to whichever semester sorted highest alphabetically.
    df = frame([
        {"student_id": "S1", "semester": "2022 Sem 2", "phonics": 1.0},
        {"student_id": "S1", "semester": "2023 Sem 1", "phonics": 7.0},
    ])
    assert latest_per_student(df).iloc[0]["phonics"] == 7.0


def test_ties_within_a_semester_break_on_the_later_sitting_date():
    """UT-2.22: two rows in one semester resolve to the later sitting."""
    # 22 student+semester pairs in the real workbook have two rows.
    df = frame([
        {"student_id": "S1", "semester": "2025 Sem 1", "phonics": 1.0,
         "_sitting_date": pd.Timestamp("2025-03-01")},
        {"student_id": "S1", "semester": "2025 Sem 1", "phonics": 8.0,
         "_sitting_date": pd.Timestamp("2025-06-01")},
    ])
    assert latest_per_student(df).iloc[0]["phonics"] == 8.0


def test_ties_with_no_date_fall_back_to_workbook_order():
    """UT-2.22: an undated tie is still deterministic."""
    # Deterministic either way: a re-ingest must never reshuffle cluster membership.
    df = frame([
        {"student_id": "S1", "semester": "2025 Sem 1", "phonics": 1.0},
        {"student_id": "S1", "semester": "2025 Sem 1", "phonics": 8.0},
    ])
    assert latest_per_student(df).iloc[0]["phonics"] == 8.0
    assert latest_per_student(df).equals(latest_per_student(df))


def test_reduction_drops_the_internal_sort_column():
    """UT-2.21: the internal sort key does not leak into the cohort frame."""
    out = latest_per_student(frame([{"student_id": "S1"}]))
    assert "_sitting_date" not in out.columns and "_row" not in out.columns


# ── writing collapse ──────────────────────────────────────────────────────────
def test_collapse_takes_the_one_genre_the_student_sat():
    """UT-2.23: the single non-zero genre becomes the writing mark."""
    df = frame([
        {"student_id": "S1", "narrative_writing": 12.0},
        {"student_id": "S2", "exposition_writing": 19.0},
        {"student_id": "S3", "persuasive_writing": 7.0},
    ])
    assert list(df.writing) == [12.0, 19.0, 7.0]
    assert list(df.writing_genre) == [
        "narrative_writing", "exposition_writing", "persuasive_writing"]


def test_all_zero_writing_is_missing_not_zero():
    """UT-2.24: The 70 students with every genre at 0 were never assessed on writing. A 0 would put
    them at the bottom of the writing axis — a claim about their ability the data never made."""
    df = frame([{"student_id": "S1"}])  # all three genres default to 0.0

    assert pd.isna(df.writing.iloc[0])
    assert pd.isna(df.writing_genre.iloc[0])


def test_absent_genre_columns_yield_no_writing_mark():
    """UT-2.24: no genre columns at all means no writing mark."""
    df = frame([{"student_id": "S1", "narrative_writing": None,
                 "exposition_writing": None, "persuasive_writing": None}])
    assert pd.isna(df.writing.iloc[0])


def test_writing_genre_audit_counts_non_zero_genres_per_student():
    """UT-2.23: the mutual-exclusivity audit counts genres per student."""
    df = frame([
        {"student_id": "S1", "narrative_writing": 12.0},   # one genre
        {"student_id": "S2"},                              # none
        {"student_id": "S3", "narrative_writing": 3.0, "persuasive_writing": 4.0},  # two
    ])
    audit = writing_genre_audit(df)

    assert audit.to_dict() == {0: 1, 1: 1, 2: 1}


# ── band grouping ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize("band, expected", [
    ("A1", "A"), ("A3", "A"), ("B4", "B"), ("B6", "B"), ("C7", "C"), ("C9", "C"),
    ("  b5 ", "B"),          # whitespace + case, as the workbook sometimes carries
    (None, UNBANDED), ("", UNBANDED), ("Z1", UNBANDED),
])
def test_band_group_reduces_the_nine_bands_to_three(band, expected):
    """UT-2.25: A1..C9 map to A/B/C; anything unrecognised is UNBANDED."""
    assert _band_group(pd.Series([band])).iloc[0] == expected


def test_band_group_is_the_clustering_scope():
    """UT-2.25: the scope is the band letter, not the fine band."""
    # Not the fine band: the assessment paper changes at the letter, which is the
    # comparability boundary clustering needs.
    df = frame([{"student_id": "S1", "band": "A1"}, {"student_id": "S2", "band": "A3"}])
    assert list(df.band_group) == ["A", "A"]


# ── coverage report ───────────────────────────────────────────────────────────
def test_coverage_reports_presence_and_spread_per_feature():
    """UT-2.26: the audit reports presence, zeros and spread per feature."""
    df = frame([
        {"student_id": "S1", "phonics": 0.0},
        {"student_id": "S2", "phonics": 40.0},
        {"student_id": "S3", "phonics": None},
    ])
    report = coverage(df, CLUSTER_FEATURES).set_index("feature")

    assert report.loc["phonics", "present"] == 2
    assert report.loc["phonics", "missing"] == 1
    assert report.loc["phonics", "zero"] == 1
    assert report.loc["phonics", "max"] == 40.0


def test_writing_is_plottable_but_not_clustered():
    """UT-2.26: writing is an axis but never a clustering feature."""
    # The distinction the dashboard depends on: four axes to choose from, three fed to k-means.
    assert "writing" in PLOT_FEATURES
    assert "writing" not in CLUSTER_FEATURES
    assert set(CLUSTER_FEATURES).issubset(PLOT_FEATURES)


# ── percentiles ───────────────────────────────────────────────────────────────
# These feed LearnerDetailPage's radar chart, whose single radius cannot carry the raw marks
# (different rubrics per axis) nor percent-of-max (different rubric per band).
def test_percentile_ranks_within_the_band_group_not_the_whole_cohort():
    """UT-2.46: the comparison population is the band group.

    THE POINT OF THE COLUMN. The bands sit different papers — phonics tops out at 25 in A1 and
    46 in A3 — so a cohort-wide rank would read "which paper did you sit" as if it were "how
    are you doing", the same confound that made the band-scoped k-means fit score better.
    Here band C's marks are all far below band A's, yet the top of each band ranks 100th.
    """
    df = frame([
        {"student_id": "A1", "band": "A2", "phonics": 10.0},
        {"student_id": "A2", "band": "A2", "phonics": 30.0},
        {"student_id": "C1", "band": "C8", "phonics": 2.0},
        {"student_id": "C2", "band": "C8", "phonics": 4.0},
    ])
    out = percentiles(df)["phonics_pct"]

    assert list(out) == [50.0, 100.0, 50.0, 100.0]


def test_a_mark_the_learner_never_received_has_no_percentile():
    """UT-2.47: NaN in, NaN out — an unassessed paper is not a rank of zero.

    Writing is never administered to band A. A 0th percentile would say the learner came last
    on a paper they never sat, and the radar chart reads `writing_pct` to decide whether the
    axis exists at all.
    """
    df = frame([
        {"student_id": "S1", "band": "A2", "narrative_writing": 12.0},
        {"student_id": "S2", "band": "A2"},   # all genres 0 -> writing is NaN
    ])
    out = percentiles(df)["writing_pct"]

    assert out.iloc[0] == 100.0
    assert pd.isna(out.iloc[1])


def test_the_only_learner_in_a_band_ranks_top_of_it():
    """UT-2.46: a band group of one is the whole of its own population."""
    # Degenerate but real: the workbook's three unbanded students group alone. 100 is the
    # honest answer — they are top of everyone they can be compared with — and the chart's
    # caption names the population, so it does not read as a cohort-wide claim.
    df = frame([{"student_id": "S1", "band": "A2", "phonics": 7.0}])
    assert percentiles(df)["phonics_pct"].iloc[0] == 100.0


def test_ties_share_a_percentile():
    """UT-2.47: equal marks rank equally.

    Not incidental: these are coarse rubric marks (word reading is an integer out of 10), so
    ties are the common case, not an edge one. Two learners with the same mark must not be
    separated by row order.
    """
    df = frame([
        {"student_id": "S1", "band": "B4", "word_reading_accuracy": 8.0},
        {"student_id": "S2", "band": "B4", "word_reading_accuracy": 8.0},
        {"student_id": "S3", "band": "B4", "word_reading_accuracy": 2.0},
    ])
    out = percentiles(df)["word_reading_accuracy_pct"]

    assert out.iloc[0] == out.iloc[1]
    assert out.iloc[2] < out.iloc[0]


def test_one_percentile_column_per_plottable_feature():
    """UT-2.46: every axis the radar can draw has a rank behind it."""
    out = percentiles(frame([{"student_id": "S1", "narrative_writing": 9.0}]))

    assert list(out.columns) == list(PERCENTILE_COLUMNS)
    assert PERCENTILE_COLUMNS == tuple(f"{f}_pct" for f in PLOT_FEATURES)


# ── latest_per_semester ───────────────────────────────────────────────────────
# The history's dedup. `learner_sittings` is keyed on (learner_id, semester), and the workbook
# holds 22 pairs of rows for one student in one semester.
def test_one_row_survives_per_student_per_semester():
    """UT-2.71: THE BUG THIS EXISTS FOR.

    Sending both rows of a tie pair makes Postgres refuse the entire 500-row batch with
    "ON CONFLICT DO UPDATE command cannot affect row a second time" — an error naming neither
    the student nor the semester, so nothing in the output points at the cause.
    """
    df = frame([
        {"student_id": "S1", "semester": "2025 Sem 1", "phonics": 1.0},
        {"student_id": "S1", "semester": "2025 Sem 1", "phonics": 8.0},   # the tie
        {"student_id": "S1", "semester": "2026 Sem 1", "phonics": 9.0},
        {"student_id": "S2", "semester": "2025 Sem 1", "phonics": 3.0},
    ])
    out = latest_per_semester(df)

    assert len(out) == 3, "one row per (student, semester), not per workbook row"
    assert not out.duplicated(subset=["student_id", "semester"]).any()


def test_the_tie_break_matches_latest_per_student():
    """UT-2.71: the history and the cohort must agree about which tie row won.

    Both go through the same ordering. If they diverged, a learner's newest point on the chart
    could carry a different mark from the one the dashboard clusters them on.
    """
    df = frame([
        {"student_id": "S1", "semester": "2026 Sem 1", "phonics": 1.0,
         "_sitting_date": pd.Timestamp("2026-03-01")},
        {"student_id": "S1", "semester": "2026 Sem 1", "phonics": 8.0,
         "_sitting_date": pd.Timestamp("2026-06-01")},
    ])

    assert latest_per_semester(df).iloc[0]["phonics"] == 8.0
    assert latest_per_student(df).iloc[0]["phonics"] == 8.0


def test_every_semester_is_kept_not_just_the_newest():
    """UT-2.72: this is a history, not a reduction to the current state.

    The distinction from `latest_per_student`, and the whole reason the chart has an X axis.
    """
    df = frame([
        {"student_id": "S1", "semester": "2022 Sem 1", "phonics": 1.0},
        {"student_id": "S1", "semester": "2024 Sem 2", "phonics": 5.0},
        {"student_id": "S1", "semester": "2026 Sem 1", "phonics": 9.0},
    ])

    assert sorted(latest_per_semester(df).semester) == [
        "2022 Sem 1", "2024 Sem 2", "2026 Sem 1"]
    assert len(latest_per_student(df)) == 1, "the cohort keeps only the newest"


def test_the_internal_sort_column_does_not_leak():
    """UT-2.72: `_sitting_date` is a tie-break, not a stored column."""
    out = latest_per_semester(frame([{"student_id": "S1"}]))
    assert "_sitting_date" not in out.columns and "_row" not in out.columns
