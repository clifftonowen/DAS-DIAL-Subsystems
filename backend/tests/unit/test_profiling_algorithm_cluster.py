"""UNIT — ProfilingAlgorithm.cluster() in isolation (UC2 cohort clustering).

    AB2.7  ProfilingAlgorithm.cluster()           UT-2.12 .. UT-2.18
    AB2.8  ProfilingAlgorithm.cluster_by_group()  UT-2.19, UT-2.20

EXTENDS THE PM3 UC2 TEST PLAN. That plan numbers UT-2.1 .. UT-2.11 and covers only the
generate-profile flow (ProfileController -> ProfilingService -> analyse -> saveProfile);
`cluster()` is declared in the class diagram but has no test ID there. These IDs continue
the sequence rather than renumbering it, so the existing plan rows stay valid.

Pure function: learner rows in, cluster labels + the silhouette evidence out. No
repository, no Supabase, no workbook. Deterministic by construction (`random_state=42`),
which is what makes exact assertions on labels legitimate here.

The fixtures build synthetic cohorts with a KNOWN answer — three well-separated blobs,
say — so a test can assert which k was chosen rather than merely that one was.
"""
import pytest

from app.agents.profiling_algorithm import K_MIN, MIN_GROUP, ProfilingAlgorithm

pytestmark = pytest.mark.unit

FEATURES = ("phonics", "word_reading_accuracy", "word_spelling")


def learner(sid, phonics=None, reading=None, spelling=None, **extra):
    return {"student_id": sid, "phonics": phonics, "word_reading_accuracy": reading,
            "word_spelling": spelling, **extra}


def blobs(centres, per_blob=25, spread=0.4):
    """`per_blob` learners jittered around each centre. Deterministic — no RNG — so the
    expected k is a property of the fixture, not of a seed."""
    rows = []
    for b, (p, r, s) in enumerate(centres):
        for i in range(per_blob):
            offset = (i % 5 - 2) * spread
            rows.append(learner(f"S{b}-{i}", p + offset, r + offset, s - offset))
    return rows


# ── choosing k ────────────────────────────────────────────────────────────────
def test_picks_the_k_matching_well_separated_blobs():
    """UT-2.12: three separated blobs -> the sweep lands on k=3."""
    # Three tight, far-apart groups: the silhouette sweep should land on exactly 3.
    run = ProfilingAlgorithm().cluster(
        blobs([(2, 1, 1), (22, 5, 5), (44, 10, 10)]), FEATURES, tier="T")

    assert run.k == 3
    assert run.best_silhouette == max(run.silhouette_by_k.values())


def test_sweeps_every_k_in_range_and_records_each_score():
    """UT-2.12: every k in the range is fitted and scored."""
    run = ProfilingAlgorithm().cluster(
        blobs([(2, 1, 1), (44, 10, 10)]), FEATURES, tier="T", k_min=2, k_max=6)

    assert sorted(run.silhouette_by_k) == [2, 3, 4, 5, 6]
    assert all(-1.0 <= v <= 1.0 for v in run.silhouette_by_k.values())


def test_k_is_capped_by_the_number_of_distinct_points():
    """UT-2.18: k can never exceed the distinct coordinates available."""
    # Only three distinct coordinates exist, so k=10 is unreachable: asking KMeans for more
    # clusters than distinct points yields empty clusters and silhouette_score raises.
    rows = [learner(f"S{i}", *[(1, 1, 1), (9, 9, 9), (5, 5, 5)][i % 3]) for i in range(60)]
    run = ProfilingAlgorithm().cluster(rows, FEATURES, tier="T", k_max=10)

    assert run.k <= 2  # distinct points (3) minus one


# ── standardisation ───────────────────────────────────────────────────────────
def test_scaling_lets_a_narrow_feature_decide_the_partition():
    """UT-2.13: The regression guard for the whole design.

    Phonics runs 0-46 and spelling 0-10, so raw Euclidean distance is dominated by phonics
    and the other skills are noise. Here phonics is spread wide but carries NO structure
    (evenly spaced), while spelling is perfectly bimodal at 1 and 9 — the real signal.

    An unscaled fit splits on phonics and gets spelling means of 4.9/5.1, i.e. it misses the
    only real group there is. A scaled fit recovers it exactly. Delete the StandardScaler
    call and this test fails.
    """
    rows = [learner(f"S{i}", phonics=i * 46 / 59, reading=5, spelling=1 if i % 2 == 0 else 9)
            for i in range(60)]

    run = ProfilingAlgorithm().cluster(rows, FEATURES, tier="T", k_min=2, k_max=2)

    low = {r["student_id"] for r in rows if r["word_spelling"] == 1}
    labels_for_low = {run.labels[s] for s in low}
    assert len(labels_for_low) == 1, "the low-spelling group was split — features not scaled"
    assert len(set(run.labels.values()) - labels_for_low) == 1

    # And the clusters differ on spelling, not on phonics — the inverse of the unscaled fit.
    by_spelling = {c["cluster"]: c["word_spelling"] for c in run.centroids}
    assert sorted(by_spelling.values()) == [1.0, 9.0]
    assert {round(c["phonics"]) for c in run.centroids} == {23}


# ── labels ────────────────────────────────────────────────────────────────────
def test_labels_are_ranked_low_to_high_by_centroid():
    """UT-2.14: labels run weakest to strongest, so the legend reads low to high."""
    run = ProfilingAlgorithm().cluster(
        blobs([(2, 1, 1), (22, 5, 5), (44, 10, 10)]), FEATURES, tier="Band")

    # "Band 1" must be the weakest group and "Band 3" the strongest — the dashboard legend
    # sorts these labels as text and reads them low to high.
    means = {c["cluster"]: sum(c[f] for f in FEATURES) for c in run.centroids}
    assert means["Band 1"] < means["Band 2"] < means["Band 3"]


def test_labels_are_zero_padded_when_k_reaches_ten():
    """UT-2.14: At k=10 an unpadded "T 10" sorts between "T 1" and "T 2" as text, which would
    scramble the legend's low-to-high reading."""
    rows = blobs([(i * 5, i % 10, (10 - i) % 10) for i in range(10)], per_blob=12, spread=0.1)
    run = ProfilingAlgorithm().cluster(rows, FEATURES, tier="T", k_min=10, k_max=10)

    assert run.k == 10
    assert sorted(set(run.labels.values())) == [f"T {i:02d}" for i in range(1, 11)]


def test_same_input_gives_identical_labels():
    """UT-2.15: same rows in, same labels out — a re-ingest cannot recolour the dashboard."""
    # random_state is fixed precisely so a re-ingest cannot recolour the dashboard.
    rows = blobs([(2, 1, 1), (22, 5, 5), (44, 10, 10)])
    first = ProfilingAlgorithm().cluster(rows, FEATURES, tier="T")
    second = ProfilingAlgorithm().cluster(rows, FEATURES, tier="T")

    assert first.labels == second.labels
    assert first.k == second.k and first.best_silhouette == second.best_silhouette


# ── missing data ──────────────────────────────────────────────────────────────
def test_rows_missing_a_feature_are_dropped_not_imputed():
    """UT-2.17: a learner missing a feature is dropped and counted, never imputed."""
    rows = blobs([(2, 1, 1), (44, 10, 10)])
    rows.append(learner("no-spelling", 20, 5, None))
    rows.append({"student_id": "no-phonics", "word_reading_accuracy": 5, "word_spelling": 5})

    run = ProfilingAlgorithm().cluster(rows, FEATURES, tier="T")

    assert run.n_skipped == 2
    assert run.n_learners == len(rows) - 2
    assert "no-spelling" not in run.labels and "no-phonics" not in run.labels


def test_nan_counts_as_missing():
    """UT-2.17: NaN is the pandas spelling of a blank cell and counts as absent."""
    # pandas spells a blank cell NaN, and NaN is a float — so a naive isinstance check
    # would let it through and poison the whole feature matrix.
    rows = blobs([(2, 1, 1), (44, 10, 10)])
    rows.append(learner("blank", float("nan"), 5, 5))

    assert ProfilingAlgorithm().cluster(rows, FEATURES, tier="T").n_skipped == 1


def test_numpy_scalars_are_accepted():
    """UT-2.17: Rows come from pandas, where an integer column yields numpy.int64 — which is not a
    subclass of int. An isinstance gate here would silently discard the entire cohort."""
    np = pytest.importorskip("numpy")
    rows = [learner(f"S{i}", np.int64(2 + i % 3), np.float64(1.0), np.int64(1)) for i in range(30)]
    rows += [learner(f"H{i}", np.int64(44 + i % 3), np.float64(10.0), np.int64(9)) for i in range(30)]

    run = ProfilingAlgorithm().cluster(rows, FEATURES, tier="T")
    assert run.n_skipped == 0 and run.n_learners == 60


def test_returns_none_when_too_few_rows_survive():
    """UT-2.16: nothing to partition is a legitimate state, not an error."""
    # An empty cohort is a legitimate state (nothing ingested yet), not an error.
    assert ProfilingAlgorithm().cluster([], FEATURES, tier="T") is None
    assert ProfilingAlgorithm().cluster(
        [learner(f"S{i}", i, i, i) for i in range(K_MIN)], FEATURES, tier="T") is None


# ── centroids ─────────────────────────────────────────────────────────────────
def test_centroids_are_in_original_units_and_sum_to_the_cohort():
    """UT-2.12: centroids are reported in original units and account for every learner."""
    run = ProfilingAlgorithm().cluster(
        blobs([(2, 1, 1), (44, 10, 10)], per_blob=30), FEATURES, tier="T")

    assert sum(c["n"] for c in run.centroids) == run.n_learners
    # Original units, not standard deviations: "phonics 44" is readable, "phonics 1.2sd" is not.
    strongest = max(run.centroids, key=lambda c: c["phonics"])
    assert 40 < strongest["phonics"] < 48


# ── grouped fitting ───────────────────────────────────────────────────────────
def test_cluster_by_group_fits_each_group_independently():
    """UT-2.19: each group gets its own fit, its own k and its own label prefix."""
    rows = ([dict(r, band_group="A") for r in blobs([(2, 1, 1), (22, 5, 5), (44, 10, 10)])]
            + [dict(r, band_group="B", student_id=f"B{r['student_id']}")
               for r in blobs([(5, 2, 2), (40, 9, 9)])])

    runs = ProfilingAlgorithm().cluster_by_group(rows, FEATURES, group_key="band_group")

    assert set(runs) == {"A", "B"}
    # Each group picks its own k off its own silhouette curve.
    assert runs["A"].k == 3 and runs["B"].k == 2
    assert all(label.startswith("A ") for label in runs["A"].labels.values())
    assert all(label.startswith("B ") for label in runs["B"].labels.values())


def test_cluster_by_group_skips_groups_below_the_minimum():
    """UT-2.20: a group too small to describe a pattern is left unlabelled."""
    rows = [dict(r, band_group="A") for r in blobs([(2, 1, 1), (44, 10, 10)], per_blob=30)]
    rows += [learner(f"tiny{i}", i, i, i, band_group="?") for i in range(3)]

    runs = ProfilingAlgorithm().cluster_by_group(rows, FEATURES, group_key="band_group")

    # Three learners are not a cohort — clustering them describes individuals, not patterns.
    assert set(runs) == {"A"}
    assert MIN_GROUP > 3
