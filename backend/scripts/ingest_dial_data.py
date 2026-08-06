"""CLI for offline cohort ingestion + clustering (run from backend/).

    python -m scripts.ingest_dial_data --file ../DIAL_Anonymised_Data.xlsx --dry-run
    python -m scripts.ingest_dial_data --file ../DIAL_Anonymised_Data.xlsx

--dry-run does everything except touch Supabase: it reads the workbook, re-checks the data
assumptions the feature selection rests on, fits every band model and prints the silhouette
sweep, k, and the centroids in original units. It needs no secrets. Always dry-run first — the
printed audit is how you notice that a new workbook has broken an assumption.

THIS SCRIPT NEVER DELETES AND NEVER RENAMES ANYONE.
    Since the 2026-08-07 merge the cohort shares the `learners` table with the therapist's
    caseload, and `learner_sittings` / `assessment_records` cascade from it. Two consequences
    shape everything below:

      * There is no --replace. A delete here could destroy generated clinical work, and no
        ingest run is worth that risk. A student dropped from a new workbook lingers as a stale
        row; that is the trade, and it is the right way round.
      * `STORED` carries ONLY workbook-derived columns. PostgREST updates the columns a payload
        carries and leaves the rest alone, so omitting `pseudonym`, `tier` and `on_caseload` is
        what stops a re-ingest erasing the caseload identity of a learner who is also in the
        cohort. Adding one of those names to STORED would silently anonymise real learners.

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
    PERCENTILE_COLUMNS,
    PLOT_FEATURES,
    SCORE_COLUMNS,
    coverage,
    latest_per_semester,
    latest_per_student,
    load_workbook,
    percentiles,
    writing_genre_audit,
)

DEFAULT_WORKBOOK = Path(__file__).resolve().parents[2] / "DIAL_Anonymised_Data.xlsx"

# Columns written to `learners`, in table order. The two cluster_* labels are added per row.
#
# EVERY NAME HERE IS DERIVED FROM THE WORKBOOK, and that is a rule, not an observation. The
# cohort shares this table with the therapist's caseload; an upsert updates the columns its
# payload carries and leaves the rest untouched, so `pseudonym`, `tier` and `on_caseload` stay
# safe precisely because they are absent. Add one and the next ingest anonymises real learners.
STORED = (
    "student_id", "semester", "band", "band_group", "school_level", "age",
    *SCORE_COLUMNS, "writing", "writing_genre", *PERCENTILE_COLUMNS,
)

# Columns written to `learner_sittings`, one row per student per semester. `learner_id` is added
# per row once the learner's uuid is known — the workbook only knows student ids.
SITTING_STORED = (
    "semester", "band", "band_group", "writing",
    *CLUSTER_FEATURES, "writing_genre", *PERCENTILE_COLUMNS,
)


def build_rows(df, band_labels: dict[str, str], cohort_labels: dict[str, str]) -> list[dict]:
    """DataFrame + both label maps -> `learners` rows, ready to upsert on student_id.

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


def build_sitting_rows(sittings, student_to_id: dict[str, str]) -> list[dict]:
    """The whole workbook -> `learner_sittings` rows, keyed by the learner's uuid.

    A sitting whose student has no `learners` row is DROPPED rather than written with a null
    FK — Postgres would reject the batch anyway, and one unresolvable student should not cost
    the other 22,891 rows. The caller reports the count.

    Same NaN -> None coercion as `build_rows`, for the same reason: NaN survives `json.dumps`
    as the bare literal `NaN`, which PostgREST rejects with a parse error naming no column.
    """
    rows = []
    for record in sittings[["student_id", *SITTING_STORED]].to_dict("records"):
        learner_id = student_to_id.get(str(record["student_id"]))
        if not learner_id:
            continue
        row = {k: (None if v is None or v != v else v)
               for k, v in record.items() if k != "student_id"}
        row["learner_id"] = learner_id
        row["semester"] = str(row["semester"])
        row["source"] = "workbook"
        rows.append(row)

    # The upsert conflicts on (learner_id, semester), and Postgres refuses a batch that proposes
    # the same pair twice — with an error that names neither the learner nor the semester. The
    # caller should have deduplicated with `latest_per_semester`; fail here, naming an offender,
    # rather than letting PostgREST reject 500 rows anonymously.
    seen, duplicates = set(), []
    for row in rows:
        key = (row["learner_id"], row["semester"])
        if key in seen:
            duplicates.append(key)
        seen.add(key)
    if duplicates:
        raise ValueError(
            f"{len(duplicates)} duplicate (learner_id, semester) pair(s) in the sittings, "
            f"e.g. {duplicates[0]}. Deduplicate with latest_per_semester() first."
        )
    return rows


def _learner_ids(learners_repo) -> dict[str, str]:
    """student_id -> learners.id for every learner that has a workbook id.

    Read back rather than generated: the uuids belong to Postgres, and a student already in the
    table must keep the one their sittings, activities and assessment records already point at.
    """
    return {
        str(row["student_id"]): row["id"]
        for row in learners_repo.list_cohort()
        if row.get("student_id")
    }


def report(df, runs: dict, cohort_run, caseload: int | None = None,
           sittings: int | None = None) -> None:
    """The audit --dry-run prints. Re-derives every claim from the workbook in front of it."""
    print(f"\ncohort: {len(df):,} students (one row each, most recent sitting)")
    print(f"semesters: {df.semester.min()} .. {df.semester.max()}")
    if sittings is not None:
        # The history behind the profile page's progress chart. The gap between this and the
        # cohort count is what the ingest used to throw away.
        print(f"history: {sittings:,} sittings across all semesters "
              f"({sittings / max(len(df), 1):.1f} per student on average)")
    print()

    print("── feature coverage " + "─" * 60)
    print(coverage(df, PLOT_FEATURES + ("fluency_mark",)).to_string(index=False))

    # Percentiles feed the learner profile's radar chart. Printed per band group because that is
    # the population each rank is taken against — a percentile that spanned bands would be
    # comparing scores from different papers, which is the whole reason for this column.
    print("\n── percentile coverage (rank within band group) " + "─" * 33)
    for feature in PLOT_FEATURES:
        column = df[f"{feature}_pct"]
        ranked = int(column.notna().sum())
        line = f"  {feature:<24} ranked {ranked:>6,} / {len(df):,}"
        if ranked:
            by_group = df.groupby("band_group")[f"{feature}_pct"].count().to_dict()
            line += f"   range {column.min():g}..{column.max():g}   by band {by_group}"
        else:
            line += "   <<< NOTHING TO RANK"
        print(line)

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

    # The caseload shares this table. Printed before the write so you can see what the upsert is
    # about to touch — these rows keep their pseudonym and tier because STORED does not carry
    # those columns, and this line is the check that the count does not move across a run.
    if caseload is not None:
        print(f"\n  caseload rows already in `learners`: {caseload:,} "
              f"(their pseudonym/tier/on_caseload are not in STORED, so the upsert leaves them)")


def cmd_run(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not path.exists():
        print(f"Workbook not found: {path}")
        return 1

    print(f"reading {path.name} ...")

    raw = load_workbook(path)

    # The learner's score history — one row per student per SEMESTER, which is what the profile
    # page's progress chart plots. Deduplicated first: the workbook holds 22 pairs of rows for
    # one student in one semester, and `learner_sittings` is keyed on exactly that pair.
    # Percentiles here rank a sitting against everyone who sat the SAME PAPER in the SAME
    # SEMESTER, so the line moves as the learner does rather than as the cohort changes — and
    # they are computed after the dedup, so a tie row cannot skew its own rank.
    sittings = latest_per_semester(raw)
    sittings = sittings.join(percentiles(sittings, by=("semester", "band_group")))

    # The cohort as the dashboard sees it: one row per student, their most recent sitting.
    # Percentiles rank against the whole band group, which is the population the radar chart's
    # caption names. Same source frame and the same tie-break, so the two can never disagree.
    df = latest_per_student(raw)
    df = df.join(percentiles(df))
    records = df.to_dict("records")

    # Two scopes, same features, same seed. The dashboard toggles between them, so both are
    # fitted here and both label columns are written — see the migration for why.
    algo = ProfilingAlgorithm()
    cohort_run = algo.cluster(records, CLUSTER_FEATURES, tier="Cohort")
    runs = algo.cluster_by_group(records, CLUSTER_FEATURES, group_key="band_group")

    if cohort_run is None or not runs:
        print("Not enough usable rows to fit both scopes — nothing to write.")
        return 1

    band_labels = {sid: label for run in runs.values() for sid, label in run.labels.items()}
    rows = build_rows(df, band_labels, cohort_run.labels)

    if args.dry_run:
        report(df, runs, cohort_run, sittings=len(sittings))
        print("\n--dry-run: nothing written.")
        return 0

    # Imported here, not at module scope, so a dry run works without Supabase configured.
    from app.repositories.clustering_run_repository import ClusteringRunRepository
    from app.repositories.learner_repository import LearnerRepository

    from app.repositories.learner_sitting_repository import LearnerSittingRepository

    learners_repo = LearnerRepository()
    report(df, runs, cohort_run,
           caseload=learners_repo.count(caseload_only=True), sittings=len(sittings))

    # Upsert only — there is no delete path. See the module docstring: `learner_sittings` and
    # `assessment_records` cascade from this table, so a stale row is a far cheaper mistake than
    # a deleted learner.
    print(f"upserting {len(rows):,} learners rows (on_conflict=student_id) ...")
    learners_repo.upsert_many(rows)

    # The history, AFTER the learners exist — every sitting carries an FK to learners(id), which
    # only the upsert above can have created for a student new to the table. Resolving the uuids
    # by reading back is what makes this survive a first run on an empty database.
    student_to_id = {
        sid: lid for sid, lid in _learner_ids(learners_repo).items()
    }
    sitting_rows = build_sitting_rows(sittings, student_to_id)
    missing = len(sittings) - len(sitting_rows)
    print(f"upserting {len(sitting_rows):,} learner_sittings rows "
          f"(on_conflict=learner_id,semester)"
          f"{f'; {missing:,} skipped, no learner row' if missing else ''} ...")
    LearnerSittingRepository().upsert_many(sitting_rows)

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
    # No --replace, by design. The cohort shares `learners` with the therapist's caseload, and
    # learner_sittings / assessment_records cascade from it — see the module docstring.
    return cmd_run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
