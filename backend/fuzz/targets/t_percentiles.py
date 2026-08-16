"""Target for `app/services/percentiles.py` — and the project's first DIFFERENTIAL oracle.

`oracles.py` has defined the DIFFERENTIAL kind since the engine was written and nothing used it,
because a differential oracle needs something most code does not have: two independent
implementations of one rule, both of which are supposed to be right.

This unit has exactly that, and says so itself:

    percentiles.py    "the request-path twin of dial_workbook.percentiles"
                      "THE TWO MUST AGREE EXACTLY. They write the same column for the same learner
                       population, and the profile page cannot tell which writer produced a row."

`percentile_of` is a hand-written ranking used on the upload path, where pandas is not available.
`dial_workbook.percentiles` is `(grouped[f].rank(pct=True) * 100).round(1)`, used at bulk ingest.
Both write `<feature>_pct` for the same learners. If they disagree, a learner's percentile moves
when the source of their marks changes and nothing on screen explains it — a wrong answer with no
exception and no log line, which is the class of defect a crash oracle cannot see at all.

The differential is the whole point, so the input decodes to a POPULATION rather than a single
mark: one input ranks every member against every other and checks all of them, which is where the
tie rule lives. Ties are not an edge case here — the docstring notes phonics has 47 distinct values
across 5,783 learners — and `method="average"` is, in its own words, "the half most likely to be
reimplemented wrongly".
"""
from __future__ import annotations

import math

import pandas as pd

from app.ingestion.dial_workbook import percentiles as workbook_percentiles
from app.services.percentiles import percentile_of
from fuzz.oracles import differential, invariant
from fuzz.targets.base import Target, as_text, register

#: How many marks one input may carry. pandas' groupby/rank costs milliseconds, so this target
#: runs orders of magnitude slower than the string ones; capping the population keeps the exec
#: rate high enough for the campaign to explore rather than grind.
MAX_POPULATION = 48

#: Real rubric shapes: coarse integer marks with heavy tying, a not-assessed learner, the
#: single-member population a brand-new semester starts with, and the empty one.
SEED_POPULATIONS = [
    b"12 12 12 15 18 22 22 30",
    b"0 0 0 0 0",
    b"7",
    b"",
    b"5 None 5 None 9",
    b"1 2 3 4 5 6 7 8 9 10",
    b"46 46 45 44 44 44 2 1 0",
    b"3.5 3.5 3.5 3.5",
    b"-1 0 1",
]

#: Numbers, the not-assessed marker, and the three float values that break ordering rules.
POPULATION_GRAMMAR = {
    "<start>": ["<marks>"],
    "<marks>": ["<mark>", "<mark> <marks>"],
    "<mark>": ["<int>", "<float>", "None", "nan", "inf", "-inf", "<int>", "<int>"],
    "<int>": ["0", "1", "2", "5", "10", "12", "25", "46", "-1", "999999"],
    "<float>": ["0.5", "3.5", "1e308", "1e-308", "0.1", "-0.0"],
}


@register
class PercentilesTarget(Target):
    name = "percentiles"
    #: `percentile_of` is documented to return a value or None for any input. It is not documented
    #: to raise, so nothing is allowed through.
    allowed = ()
    oracles = ("crash", "hang", "invariant", "differential")
    max_size = 4096
    measured = "app.services"
    grammar = POPULATION_GRAMMAR

    def seeds(self) -> list[bytes]:
        return list(SEED_POPULATIONS)

    def run(self, data: bytes) -> None:
        population = _as_population(as_text(data))

        # Contract first, on every member: the range and the None rule.
        results: list[float | None] = []
        for mark in population:
            got = percentile_of(mark, population)
            results.append(got)
            if got is None:
                # None means "cannot be ranked", and the docstring names both causes.
                invariant(
                    mark is None or not any(m is not None for m in population),
                    f"percentile_of returned None for a rankable mark {mark!r}",
                )
                continue
            invariant(
                isinstance(got, (int, float)) and not isinstance(got, bool),
                f"percentile_of returned {got!r}",
            )
            invariant(
                math.isfinite(got),
                f"percentile_of returned the non-finite {got!r} for mark {mark!r}",
            )
            invariant(
                0.0 < got <= 100.0,
                f"percentile_of returned {got} for mark {mark!r}, outside the documented 0-100",
            )

        # Order independence: a percentile is a property of the mark within the population, not of
        # the order the rows arrived in. The workbook groups rows, so it has no order to depend on;
        # if the hand-written twin does, the two disagree on the same data.
        if len(population) > 1:
            reversed_population = list(reversed(population))
            for mark, got in zip(population, results):
                again = percentile_of(mark, reversed_population)
                invariant(
                    _same(got, again),
                    f"percentile_of gave {got!r} then {again!r} for {mark!r} on a reordered "
                    f"population of the same {len(population)} marks",
                )

        # THE DIFFERENTIAL. Rank the whole population through pandas the way the workbook does and
        # require agreement mark for mark.
        expected = _workbook_reference(population)
        if expected is None:
            return
        for mark, got, want in zip(population, results, expected):
            differential(
                _same(got, want),
                f"percentile_of({mark!r}) = {got!r} but dial_workbook.percentiles gives {want!r} "
                f"for the same population of {len(population)} marks",
            )


def _as_population(text: str) -> list[float | None]:
    """Decode whitespace/comma separated tokens into marks. Unparseable tokens become None.

    Mapping junk to None rather than dropping it is deliberate: None is the not-assessed marker
    the real data carries (2,084 band A learners have no writing mark), so a mutation that
    corrupts a number into garbage still produces a population shape the code must handle.
    """
    marks: list[float | None] = []
    for token in text.replace(",", " ").split()[:MAX_POPULATION]:
        try:
            marks.append(float(token))
        except ValueError:
            marks.append(None)
    return marks


def _workbook_reference(population: list[float | None]) -> list[float | None] | None:
    """The same population ranked by `dial_workbook.percentiles`, or None if it cannot be built.

    One group, one feature — the minimum shape that exercises the same `rank(pct=True)` call the
    workbook uses. An empty population has nothing for pandas to rank, and NaN is how pandas
    spells the not-assessed marker, so `None` maps to `float("nan")` on the way in and back to
    `None` on the way out.
    """
    if not population:
        return None
    frame = pd.DataFrame({
        "mark": [float("nan") if m is None else m for m in population],
        "band_group": ["A"] * len(population),
    })
    ranked = workbook_percentiles(frame, features=("mark",), by=("band_group",))
    return [None if pd.isna(v) else float(v) for v in ranked["mark_pct"]]


def _same(left: float | None, right: float | None) -> bool:
    """Equality that treats None as a value and tolerates float rounding.

    Both sides round to one decimal place, so they should agree exactly; the tolerance exists only
    so a 0.1-vs-0.1 representation difference is not reported as a disagreement between the two
    ranking rules, which would bury the real ones.
    """
    if left is None or right is None:
        return left is None and right is None
    if math.isnan(left) or math.isnan(right):
        return math.isnan(left) and math.isnan(right)
    return abs(left - right) < 0.05
