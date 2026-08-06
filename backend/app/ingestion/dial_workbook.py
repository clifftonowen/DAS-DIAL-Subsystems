"""Reader for DIAL_Anonymised_Data.xlsx — the DAS cohort workbook (Subsystem 2).

One row in the workbook is one *sitting*: a student assessed in a given semester. A student
appears up to 10 times across the nine semesters on record (2022 Sem 1 -> 2026 Sem 1). Cohort
clustering wants one row per *student*, so `load_latest_per_student` reduces the workbook to
each student's most recent sitting.

Both the exploration notebook and `scripts/ingest_dial_data.py` import this module rather than
re-implementing the reduction, so the picture in the notebook and the rows in Supabase can
never disagree.

WHAT IS AND IS NOT A CLUSTERING FEATURE
    Three workbook columns that look like features are deliberately absent from FEATURES_FULL:

    * FluencyMark is 2 x Word_Reading_Accuracy, gated at 8 (WRA 8->16, 9->18, 10->20, and null
      for WRA <= 7 — measured across all 22,892 rows, zero exceptions). It is perfectly
      collinear, so feeding it to k-means would silently double the weight of word reading
      while costing the 930 students whose WRA is too low to have one. It is still read and
      stored (therapists use it), just never clustered on. `notebooks/subsystem2_clustering.ipynb`
      shows the crosstab this claim rests on.
    * LS_Comprehension and RD_Comprehension are 0 in every row that has them at all. A column
      with no variance cannot separate anyone, so they are not read.

THE THREE WRITING COLUMNS ARE ONE FEATURE, NOT THREE
    Narrative / Exposition / Persuasive Writing are MUTUALLY EXCLUSIVE. Each student sits
    exactly one genre and the other two columns are recorded as 0 — measured: of the 3,769
    students with any writing data, 3,699 have exactly one non-zero genre and 70 have none.
    Nobody has two. The pairwise correlations are negative (narrative/exposition -0.63)
    because they are alternatives, not because writing skills trade off.

    So those zeros mean "not assessed", not "scored zero". Clustering on the three columns
    separately partitions students by WHICH GENRE THEY SAT — the first attempt produced
    exactly three clusters of 2937/645/187, matching the genre counts — which is a fact about
    DAS's assessment schedule, not about the learners.

    `writing` therefore collapses them into the single 0-24 rubric mark the student actually
    received, and `writing_genre` keeps which one it was as an attribute the dashboard can
    display but k-means never sees.

WHY CLUSTERING IS SCOPED TO A BAND GROUP
    The scores are not on a common scale across bands, because they are not the same paper.
    Phonics tops out at 25 in band A1, 30 in A2 and 46 in A3, then falls away through B and C
    (max 17 in C9) as phonics stops being assessed. Writing is never administered to band A at
    all. Phonics is also the only feature with real spread (sd 13.1, against 1.6 for word
    reading and 3.2 for spelling), so it dominates the distance metric.

    Cluster the whole cohort at once and k-means substantially recovers *which paper the
    student sat*: the first attempt's high-phonics cluster was 56.8% band A3. Fitting within
    A / B / C instead compares like with like, and scores better for it — silhouette 0.43 /
    0.42 / 0.34 against 0.36 cohort-wide. `band_group` is that scoping key.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

SHEET = "Anonymised_Data"

# ── Feature groups ───────────────────────────────────────────────────────────
# Defined in `dial_features`, which carries no pandas import, so the running API can name these
# features and their rubric ceilings without pulling in an analysis-only dependency. Re-exported
# here because this module is where the notebook and the ingest script have always imported them
# from — see that module's docstring for why the two are split.
from app.ingestion.dial_features import (  # noqa: E402,F401  (re-export)
    CLUSTER_FEATURES,
    FEATURE_LABELS,
    FEATURE_MAXIMA,
    GENRE_COLUMNS,
    PERCENTILE_COLUMNS,
    PLOT_FEATURES,
    SCORE_COLUMNS,
    UNBANDED,
)

# ── Workbook header -> `learners` column ─────────────────────────────────
# The workbook's own spelling on the left; nothing downstream should ever see the left-hand
# names, so this map is the only place they appear.
COLUMN_MAP: dict[str, str] = {
    "Student_ID": "student_id",
    "Semester": "semester",
    "NewBand": "band",
    "SchLevel": "school_level",
    "Age": "age",
    "Phonics": "phonics",
    "Word_Reading_Accuracy": "word_reading_accuracy",
    "Word_Spelling": "word_spelling",
    "Narrative_Writing": "narrative_writing",
    "Exposition_Writing": "exposition_writing",
    "Persuasive_Writing": "persuasive_writing",
    "FluencyMark": "fluency_mark",
}

# Per-subtest date columns, used only to break ties between two sittings in the same semester
# (22 such pairs exist). Not stored — the semester is the meaningful timestamp.
DATE_COLUMNS: tuple[str, ...] = (
    "Phonics_Date", "WRA_Date", "WS_Date", "NW_Date", "EW_Date", "PW_Date",
)

# Excel's day-zero. Serial 1 is 1900-01-01, and Excel wrongly believes 1900 was a leap year,
# so the epoch that makes every real date come out right is 1899-12-30, not 1899-12-31.
_EXCEL_EPOCH = pd.Timestamp("1899-12-30")


def load_workbook(path: str | Path) -> pd.DataFrame:
    """The whole workbook, renamed to `learners` columns. One row per sitting."""
    raw = pd.read_excel(path, sheet_name=SHEET)

    missing = [c for c in COLUMN_MAP if c not in raw.columns]
    if missing:
        # A silent rename miss would present as an all-null feature and cluster every student
        # into one blob, so fail loudly and name the column.
        raise ValueError(f"{Path(path).name} is missing expected column(s): {missing}")

    df = raw.rename(columns=COLUMN_MAP)
    df["_sitting_date"] = _sitting_date(raw)

    keep = list(COLUMN_MAP.values()) + ["_sitting_date"]
    df = df[keep]

    # Scores arrive as object dtype whenever the column holds a stray blank; coerce so the
    # feature matrix is numeric and genuine blanks become NaN rather than the string "".
    for column in SCORE_COLUMNS + ("age",):
        df[column] = pd.to_numeric(df[column], errors="coerce")

    df["student_id"] = df["student_id"].astype("string").str.strip()
    df["semester"] = df["semester"].astype("string").str.strip()

    df["writing"], df["writing_genre"] = _collapse_writing(df)
    df["band_group"] = _band_group(df["band"])
    return df


def _latest_by(df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """The last row per `keys`, under one shared ordering rule.

    THE ORDERING IS THE WHOLE POINT, and both callers must share it or the cohort and the
    history could disagree about which of a student's two rows in one semester is real.

    Recency is the `semester` string. Those sort chronologically as text ("2022 Sem 1" <
    "2022 Sem 2" < "2023 Sem 1"), which holds for every value in the workbook and keeps the
    rule readable; there is no date column that covers all rows.

    Ties — a student with TWO rows in one semester, of which the workbook has 22 pairs — fall
    through to the latest subtest date, then to workbook order. Both tie-breaks are
    deterministic, so re-running the ingest can never reshuffle who is in which cluster.
    """
    ordered = (
        df.reset_index(names="_row")
          .sort_values(["student_id", "semester", "_sitting_date", "_row"],
                       na_position="first", kind="stable")
    )
    latest = ordered.groupby(keys, as_index=False, sort=True).tail(1)
    return latest.drop(columns=["_row", "_sitting_date"]).reset_index(drop=True)


def latest_per_student(df: pd.DataFrame) -> pd.DataFrame:
    """One row per student — their most recent sitting. The cohort as clustering sees it."""
    return _latest_by(df, ["student_id"])


def latest_per_semester(df: pd.DataFrame) -> pd.DataFrame:
    """One row per student PER SEMESTER — the score history, deduplicated.

    NOT the same as the raw workbook. Those 22 tie pairs are two rows for one student in one
    semester, and `learner_sittings` is keyed on exactly that pair: sending both makes Postgres
    refuse the whole batch with

        ON CONFLICT DO UPDATE command cannot affect row a second time

    which names no student and no semester. Resolving them here, with the same tie-break
    `latest_per_student` uses, means the history and the cohort agree about which row won.
    """
    return _latest_by(df, ["student_id", "semester"])


def load_latest_per_student(path: str | Path) -> pd.DataFrame:
    """The cohort as clustering sees it: one row per student, their most recent sitting."""
    return latest_per_student(load_workbook(path))


def coverage(df: pd.DataFrame, features: tuple[str, ...] = PLOT_FEATURES) -> pd.DataFrame:
    """Per-feature completeness and spread — the audit the notebook and --dry-run both print.

    `distinct` is the column that matters most here: these are coarse rubric marks, not
    continuous measures, so a feature with 11 distinct values produces many exactly-coincident
    points and a lower silhouette than a textbook example would suggest.
    """
    return pd.DataFrame(
        [
            {
                "feature": f,
                "present": int(df[f].notna().sum()),
                "missing": int(df[f].isna().sum()),
                "zero": int((df[f] == 0).sum()),
                "min": df[f].min(),
                "max": df[f].max(),
                "mean": round(float(df[f].mean()), 2),
                "sd": round(float(df[f].std()), 2),
                "distinct": int(df[f].nunique()),
            }
            for f in features
        ]
    )


def percentiles(
    df: pd.DataFrame,
    features: tuple[str, ...] = PLOT_FEATURES,
    by: tuple[str, ...] = ("band_group",),
) -> pd.DataFrame:
    """One `<feature>_pct` column per feature — the learner's percentile within `by`.

    TWO CALLERS, TWO POPULATIONS, and the difference matters:

      by=("band_group",)              the cohort as the dashboard sees it — one row per student,
                                      their latest sitting, ranked against everyone in their band
      by=("semester", "band_group")   one row per SITTING, ranked against everyone who sat that
                                      same paper that same semester

    The second is what the profile page's progress line needs. Ranking a 2022 mark against the
    2026 population would make the line move as the cohort around the learner changes rather
    than as the learner does, which is the opposite of what a progress chart is for.

    WHY A PERCENTILE AT ALL. The radar chart shares one radius across all four axes, so it
    cannot plot raw marks: phonics is out of 46, word reading out of 10. Nor can it plot
    percent-of-max,
    because the rubric itself differs by band — phonics tops out at 25 in A1, 30 in A2 and 46 in
    A3 (see WHY CLUSTERING IS SCOPED TO A BAND GROUP above). 67% of a band A1 paper and 67% of a
    band A3 paper are not the same achievement, and a radar that drew them at the same radius
    would say they were.

    Percentile within `band_group` is the same fix, for the same reason, as scoping the k-means
    fit to a band group: it compares each learner against the population that sat their paper.

    Computed here at ingest, not per request. The API is a plain SELECT over stored columns —
    the same rule the cluster labels follow — so rendering one learner's radar never reads the
    other 5,782 rows.

    NaN in, NaN out: a learner not assessed on a feature (band A and writing, 2,084 of them) has
    no percentile, exactly as `_collapse_writing` leaves them no mark. `rank` skips NaN natively.
    """
    out = pd.DataFrame(index=df.index)
    # dropna=False so a learner with no band group is still ranked — against the other unbanded
    # learners, which is a small population but an honest one. Dropping them would leave those
    # rows with no percentile at all and silently unplottable.
    grouped = df.groupby(list(by), dropna=False)
    for f in features:
        # pct=True gives 0 < rank <= 1 within the group; "average" (the default) is the right
        # tie-break for coarse rubric marks, where dozens of learners share a score.
        out[f"{f}_pct"] = (grouped[f].rank(pct=True) * 100).round(1)
    return out


def writing_genre_audit(df: pd.DataFrame) -> pd.Series:
    """How many genres each student has a non-zero mark in.

    The evidence for collapsing them: this is `{0: 70, 1: 3699}` on the real workbook — no
    student anywhere has two. Printed by the notebook and by `ingest_dial_data --dry-run`, so
    the assumption is re-checked against the data every time rather than trusted forever.
    """
    present = df[list(GENRE_COLUMNS)].dropna()
    return (present > 0).sum(axis=1).value_counts().sort_index()


# ── helpers ──────────────────────────────────────────────────────────────────
def _collapse_writing(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """(mark, genre) — the one writing score a student actually received.

    All three genres share the same 0-24 rubric, so the non-zero one IS the student's
    writing mark. Students with all three at zero were not assessed on writing at all
    (70 of them), and get NaN rather than 0 — a 0 would place them at the bottom of the
    writing axis, which is a claim about their ability that the data does not make.
    """
    genres = df[list(GENRE_COLUMNS)]
    assessed = genres.max(axis=1)
    scored = assessed > 0

    mark = assessed.where(scored)
    # idxmax only on the rows that have a winner: calling it on an all-NaN row is deprecated
    # in pandas 2.x and raises in 3.x.
    genre = pd.Series(pd.NA, index=df.index, dtype="string")
    genre.loc[scored] = genres.loc[scored].idxmax(axis=1)
    return mark, genre


def _band_group(band: pd.Series) -> pd.Series:
    """'A3' -> 'A'. The clustering scope — see the module docstring.

    The nine bands (A1-A3, B4-B6, C7-C9) are too fine to fit separately: C9 has 303 students
    and the smaller ones would give partitions nobody could act on. The letter is the level at
    which the assessment paper changes, which is exactly the comparability boundary we need.
    """
    letter = band.astype("string").str.strip().str.upper().str[0]
    return letter.where(letter.isin(["A", "B", "C"]), UNBANDED)


def _sitting_date(raw: pd.DataFrame) -> pd.Series:
    """Latest subtest date on a row, as a Timestamp; NaT when the row carries none.

    The workbook mixes two encodings in the same column — "23/04/2022" for rows typed by hand
    and the Excel serial 44717 for rows entered as dates — so both are parsed and combined.
    """
    parsed = []
    for column in DATE_COLUMNS:
        if column not in raw.columns:
            continue
        values = raw[column]
        text = pd.to_datetime(values, format="%d/%m/%Y", errors="coerce")
        serial = pd.to_numeric(values, errors="coerce")
        # Guard the serial branch: only values in a plausible date range convert, so a stray
        # small integer cannot become 1900-01-05 and win a tie-break.
        serial = _EXCEL_EPOCH + pd.to_timedelta(
            serial.where(serial.between(20000, 60000)), unit="D"
        )
        parsed.append(text.fillna(serial))

    if not parsed:
        return pd.Series(pd.NaT, index=raw.index)
    return pd.concat(parsed, axis=1).max(axis=1)
