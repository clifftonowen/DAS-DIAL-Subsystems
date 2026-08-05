"""CLI for offline cohort ingestion + clustering (run from backend/).

    python -m scripts.ingest_dial_data --file ../DIAL_Anonymised_Data.xlsx --dry-run
    python -m scripts.ingest_dial_data --file ../DIAL_Anonymised_Data.xlsx

--dry-run does everything except touch Supabase: it reads the workbook, re-checks the data
assumptions the feature selection rests on, fits every band model and prints the silhouette
sweep, k, and the centroids in original units. It needs no secrets. Always dry-run first — the
printed audit is how you notice that a new workbook has broken an assumption.

This is the ONLY place clustering runs. The API serves the labels as columns and never fits a
model, which is why /dashboard/clusters is a plain SELECT.

The working-out behind every choice here — why FluencyMark is excluded, why the writing genres
collapse to one mark, why the fit is scoped to a band group — is in
`notebooks/subsystem2_clustering.ipynb`. Both import the same two modules, so they cannot drift.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from app.agents.profiling_algorithm import K_MAX, K_MIN, ProfilingAlgorithm
from app.ingestion.dial_workbook import (
    CLUSTER_FEATURES,
    PLOT_FEATURES,
    SCORE_COLUMNS,
    coverage,
    load_latest_per_student,
    writing_genre_audit,
)

DEFAULT_WORKBOOK = Path(__file__).resolve().parents[2] / "DIAL_Anonymised_Data.xlsx"

# Columns written to learner_scores, in table order. The two cluster_* labels are added per row.
STORED = (
    "student_id", "semester", "band", "band_group", "school_level", "age",
    *SCORE_COLUMNS, "writing", "writing_genre",
)


def build_rows(df, band_labels: dict[str, str], cohort_labels: dict[str, str]) -> list[dict]:
    """DataFrame + both label maps -> learner_scores rows.

    A student may be absent from either map, and for different reasons: no band group means no
    band model was fitted for them, while a missing cohort label would mean a missing score.
    `.get` leaves the column null in both cases rather than guessing.

    NaN must become None: it is a float, so it survives `json.dumps` as the literal `NaN`,
    which is not valid JSON and which PostgREST rejects with a parse error rather than
    anything that names the column.
    """
    rows = []
    for record in df[list(STORED)].to_dict("records"):
        row = {k: (None if v is None or v != v else v) for k, v in record.items()}
        row["student_id"] = str(row["student_id"])
        row["age"] = int(row["age"]) if row["age"] is not None else None
        row["cluster_band"] = band_labels.get(row["student_id"])
        row["cluster_cohort"] = cohort_labels.get(row["student_id"])
        rows.append(row)
    return rows


def report(df, runs: dict, cohort_run) -> None:
    """The audit --dry-run prints. Re-derives every claim from the workbook in front of it."""
    print(f"\ncohort: {len(df):,} students (one row each, most recent sitting)")
    print(f"semesters: {df.semester.min()} .. {df.semester.max()}\n")

    print("── feature coverage " + "─" * 60)
    print(coverage(df, PLOT_FEATURES + ("fluency_mark",)).to_string(index=False))

    # Both of these are assumptions the feature selection depends on, so they are re-checked
    # against the data on every run rather than trusted from the day they were measured.
    print("\n── assumption checks " + "─" * 59)
    genre_counts = writing_genre_audit(df)
    multi = int(genre_counts.drop(index=[0, 1], errors="ignore").sum())
    print(f"  writing genres per student : {genre_counts.to_dict()}")
    print(f"  students with 2+ genres    : {multi} "
          f"{'OK (mutually exclusive)' if multi == 0 else '<<< ASSUMPTION BROKEN'}")

    pairs = df.dropna(subset=["fluency_mark", "word_reading_accuracy"])
    exact = (pairs.fluency_mark == 2 * pairs.word_reading_accuracy).mean() if len(pairs) else 0
    print(f"  fluency == 2 x word_reading: {exact:.1%} "
          f"{'OK (collinear, excluded)' if exact > 0.99 else '<<< NO LONGER COLLINEAR'}")

    def show(title: str, run) -> None:
        print(f"\n  {title}   n={run.n_learners:,}   k={run.k}   "
              f"silhouette={run.best_silhouette}")
        print("    sweep: " + "  ".join(f"k{k}={v:.3f}" for k, v in sorted(run.silhouette_by_k.items())))
        header = f"    {'cluster':<10}{'n':>7}" + "".join(f"{f:>24}" for f in run.features)
        print(header); print("    " + "-" * (len(header) - 4))
        for c in run.centroids:
            print(f"    {c['cluster']:<10}{c['n']:>7}" + "".join(f"{c[f]:>24}" for f in run.features))

    print(f"\n── models (k chosen from {K_MIN}..{K_MAX} by silhouette) " + "─" * 31)
    show("COHORT   ", cohort_run)
    for group, run in runs.items():
        show(f"band {group}   ", run)

    # The comparison is the reason both are stored. Band scoping wins because the assessment
    # papers differ by band — phonics tops out at 25 in A1, 30 in A2, 46 in A3 — so a single
    # cohort fit partly recovers which paper the student sat rather than how they are doing.
    band_mean = sum(r.best_silhouette for r in runs.values()) / len(runs)
    print(f"\n  cohort silhouette {cohort_run.best_silhouette:.3f}   vs   "
          f"band mean {band_mean:.3f}   "
          f"({'band scoping scores better' if band_mean > cohort_run.best_silhouette else 'cohort scores better'})")

    labelled = sum(r.n_learners for r in runs.values())
    print(f"\n  cluster_band:   {labelled:,} / {len(df):,} labelled "
          f"({len(df) - labelled} in groups below the minimum size, stored null)")
    print(f"  cluster_cohort: {cohort_run.n_learners:,} / {len(df):,} labelled "
          f"({len(df) - cohort_run.n_learners} missing a clustering feature, stored null)")


def cmd_run(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not path.exists():
        print(f"Workbook not found: {path}")
        return 1

    print(f"reading {path.name} ...")
    df = load_latest_per_student(path)
    records = df.to_dict("records")

    # Two scopes, same features, same seed. The dashboard toggles between them, so both are
    # fitted here and both label columns are written — see the migration for why.
    algo = ProfilingAlgorithm()
    cohort_run = algo.cluster(records, CLUSTER_FEATURES, tier="Cohort")
    runs = algo.cluster_by_group(records, CLUSTER_FEATURES, group_key="band_group")

    if cohort_run is None or not runs:
        print("Not enough usable rows to fit both scopes — nothing to write.")
        return 1

    report(df, runs, cohort_run)

    if args.dry_run:
        print("\n--dry-run: nothing written.")
        return 0

    # Imported here, not at module scope, so a dry run works without Supabase configured.
    from app.repositories.learner_score_repository import (
        ClusteringRunRepository, LearnerScoreRepository)

    band_labels = {sid: label for run in runs.values() for sid, label in run.labels.items()}
    rows = build_rows(df, band_labels, cohort_run.labels)

    scores_repo = LearnerScoreRepository()
    if args.replace:
        print("\nclearing learner_scores ...")
        scores_repo.delete_all()

    print(f"upserting {len(rows):,} learner_scores rows ...")
    scores_repo.upsert_many(rows)

    def as_row(run, scope: str) -> dict:
        return {
            "scope": scope,
            "tier": run.tier,
            "features": list(run.features),
            "k": run.k,
            "best_silhouette": run.best_silhouette,
            # jsonb keys must be strings.
            "silhouette_by_k": {str(k): v for k, v in run.silhouette_by_k.items()},
            "n_learners": run.n_learners,
        }

    # Appended, not replaced: previous fits stay inspectable and the service reads the newest
    # per (scope, tier).
    run_rows = [as_row(cohort_run, "cohort")] + [as_row(r, "band") for r in runs.values()]
    ClusteringRunRepository().save_many(run_rows)
    print(f"wrote {len(run_rows)} clustering_runs rows "
          f"(1 cohort + {len(runs)} band). Done.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Load the DAS cohort workbook, cluster it, and write both to Supabase.")
    parser.add_argument("--file", default=str(DEFAULT_WORKBOOK),
                        help=f"workbook path (default: {DEFAULT_WORKBOOK.name} at the repo root)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the audit and the fitted models; write nothing, need no secrets")
    parser.add_argument("--replace", action="store_true",
                        help="delete learner_scores before loading, dropping students no longer "
                             "in the workbook (upsert alone would leave them behind)")
    return cmd_run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
