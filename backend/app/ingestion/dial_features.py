"""The DIAL feature taxonomy — which marks exist, what they are called, what they are out of.

SEPARATE FROM `dial_workbook` ON PURPOSE. That module imports pandas, which is in
requirements-analysis.txt (the notebook and the ingest script), NOT in the API's runtime deps —
the running service never reads the workbook. But the service DOES need to name these features
and their rubric ceilings to serve GET /learners/{id}/overview, so the metadata lives here where
it can be imported without pandas. `dial_workbook` re-exports everything below, so the notebook
and the ingest script keep importing from the module they always did.

WHY `max` IS SERVED RATHER THAN HARDCODED IN THE UI: the frontend needs it to render "31/46"
next to a percentile, and a second copy of the rubric in constants.js is a second thing to get
wrong when a paper changes.

The `max` values are the ceiling of the hardest paper in the family (phonics reaches 46 in band
A3; it tops out lower in A1 and A2, and lower again through B and C). That makes `raw/max` a
poor cross-band comparison, which is exactly why the radar chart plots the percentile within the
learner's band group instead — see `dial_workbook.percentiles`.
"""
from __future__ import annotations

# key -> (display label, top of the rubric). Order is the order the dashboard offers them in.
DIAL_FEATURES: dict[str, tuple[str, float]] = {
    "phonics":               ("Phonics",       46.0),
    "word_reading_accuracy": ("Word Reading",  10.0),
    "word_spelling":         ("Word Spelling", 10.0),
    "writing":               ("Writing",       24.0),
}

FEATURE_LABELS: dict[str, str] = {k: v[0] for k, v in DIAL_FEATURES.items()}
FEATURE_MAXIMA: dict[str, float] = {k: v[1] for k, v in DIAL_FEATURES.items()}

# Denominator for the 0-10 normalisation the RETRIEVAL QUERY ranks on — the rubric ceiling rounded
# UP to a round number. Deliberately separate from FEATURE_MAXIMA, which is the exact ceiling the
# UI renders ("31/46") and is served as DialMetric.max; that one must stay exact.
#
# ONE CEILING PER FEATURE, NOT PER BAND, and that is a known approximation. Phonics tops out at 25
# in A1 and 30 in A2, so a lower-band learner scores lower here than their paper warrants — a
# perfect 25/25 reads as 5.0/10. Accepted because no per-band ceiling is recorded anywhere in the
# schema, the workbook or the parsed reports, and `learners.band` is null for many learners. The
# fix, if this bites, is a table keyed on the FINE band rather than the feature.
#
# Rounding up also costs a little: 46 -> 50 makes every phonics score read ~8% lower than exact
# division would, which nudges phonics toward being picked as a weakness. Uniform across learners,
# so it moves the metric's baseline rather than distorting one learner against another.
NORMALISATION_CEILINGS: dict[str, float] = {
    "phonics":               50.0,   # exact ceiling 46
    "word_reading_accuracy": 10.0,
    "word_spelling":         10.0,
    "writing":               30.0,   # exact ceiling 24
}


def normalised_score(key: str, raw: float | None) -> float | None:
    """One mark as a 0-10 score, or None if it was never assessed.

    The single definition of that score, because two callers must agree on it: the retrieval query
    ranks metrics by it (ActivityGenerationService.build_query) and the prompt states it back to
    the model (activity_prompts._fmt_mark). Two copies would eventually disagree, and the prompt
    would then cite a number the query did not act on.

    NOT ASSESSED IS NOT ZERO. None in, None out — a learner who never sat the writing paper (all
    of band A) must not be scored 0/10 on it and handed a writing activity.

    Clamped at 10: the ceiling is rounded up, so a full 46/46 phonics gives 9.2, but a mark above
    the rounded ceiling should still read as mastery rather than overflow the scale.
    """
    if not isinstance(raw, (int, float)):
        return None
    return min(raw / NORMALISATION_CEILINGS[key] * 10, 10.0)

# ── Feature groups ───────────────────────────────────────────────────────────
# What k-means actually sees. Complete for all 5,783 students, so every learner gets a label.
CLUSTER_FEATURES: tuple[str, ...] = (
    "phonics",
    "word_reading_accuracy",
    "word_spelling",
)

# What the dashboard offers as scatter axes, and what the profile radar chart plots: the three
# above plus `writing`. Writing is plottable but NOT clustered — it is never administered to
# band A, so including it would drop 2,084 learners and, before band scoping, act as a proxy for
# band membership. Four axes give the three dropdowns a real choice; three would not.
PLOT_FEATURES: tuple[str, ...] = CLUSTER_FEATURES + ("writing",)

# The raw genre columns behind `writing`. Read to build it, stored for provenance, never
# clustered on individually — see the `dial_workbook` module docstring.
GENRE_COLUMNS: tuple[str, ...] = (
    "narrative_writing",
    "exposition_writing",
    "persuasive_writing",
)

# Every numeric column carried through to `learners`.
SCORE_COLUMNS: tuple[str, ...] = CLUSTER_FEATURES + GENRE_COLUMNS + ("fluency_mark",)

# `<feature>_pct` — the percentile columns `dial_workbook.percentiles()` produces.
PERCENTILE_COLUMNS: tuple[str, ...] = tuple(f"{f}_pct" for f in PLOT_FEATURES)

# Sentinel for a student whose NewBand is missing or unrecognised. Kept as a group of its own
# rather than dropped: they are real learners, and a separate small fit is more honest than
# folding them into a band whose test they may not have sat.
UNBANDED = "?"
