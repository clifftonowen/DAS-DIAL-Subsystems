"""Percentile of one mark within its peer population — the request-path twin of
`dial_workbook.percentiles`.

WHY THIS EXISTS SEPARATELY. The workbook computes percentiles for ~22,892 sittings at ingest with
pandas. UC1's upload adds ONE sitting at a time, on the request path, where pandas is not
available: it lives in requirements-analysis.txt and the running API never imports it (see the
`dial_features` docstring for why that separation is deliberate).

THE TWO MUST AGREE EXACTLY. They write the same column for the same learner population, and the
profile page cannot tell which writer produced a row. If the rules differ, a learner's percentile
jumps when the source of their marks changes — from an uploaded assessment to a workbook re-ingest
— with nothing on screen to explain it. `test_percentiles.py` pins the two against each other.

The rule being matched, from `dial_workbook.percentiles`:

    (grouped[f].rank(pct=True) * 100).round(1)

pandas' default `method="average"` is the tie rule, which the workbook chose deliberately: these
are coarse rubric marks (phonics has 47 distinct values across 5,783 learners), so dozens of
learners share a score and the tie-break is not an edge case. Note this is NOT SQL's `cume_dist()`
used by infra/seed.sql, which ranks ties at the TOP of their group rather than the middle.
"""
from __future__ import annotations


def percentile_of(mark: float | None, population: list[float | None]) -> float | None:
    """`mark`'s percentile within `population`, 0-100, or None if it cannot be ranked.

    `population` MUST already include this learner's own mark — pandas ranks each row within its
    group, self included, so excluding it here would shift every percentile by one rank and the
    two writers would disagree by a little on every learner.

    Ties share a percentile, via the average of the ranks they span: three learners tied at ranks
    4, 5 and 6 all score the rank-5 percentile. This is what `method="average"` means and it is
    the half most likely to be reimplemented wrongly.

    Returns None — never 0, never 100 — when there is nothing to rank against:

        mark is None            not assessed. No mark, no percentile; the radar omits the axis.
        population is empty     the first sitting of a brand-new semester has no peers yet.

    A percentile of 0 would say "bottom of the cohort", which is a claim about the learner. None
    says "we cannot tell", which is the truth, and the UI already renders it as an omitted axis
    rather than a point at the origin.
    """
    if mark is None:
        return None

    marks = [m for m in population if m is not None]
    if not marks:
        return None

    less = sum(1 for m in marks if m < mark)
    equal = sum(1 for m in marks if m == mark)
    if equal == 0:
        # `mark` is not in the population it is being ranked against — the caller forgot to
        # include it. Rank it where it falls rather than silently returning a percentile that is
        # off by one rank; `less + 1` is the position it would occupy.
        average_rank = less + 1
    else:
        # The average of the ranks the tied group spans: ranks less+1 … less+equal.
        average_rank = less + (equal + 1) / 2

    return round(average_rank / len(marks) * 100, 1)
