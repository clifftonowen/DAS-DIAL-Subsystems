"""UNIT — the two helpers UC1's upload needs on the request path: percentiles and semesters.

Both exist because the workbook's versions live in `dial_workbook`, which imports pandas — an
analysis-only dependency the running API deliberately does not have. That split is fine right up
until the two implementations disagree, which is what most of this file is about.

    UT-1.11        percentile_of — the ranking rule, incl. ties and empty populations
    UT-1.12        percentile_of AGREES WITH pandas, case for case
    UT-1.13        semesters — the format, the sequence, and the form's option list
"""
import pytest

from app.ingestion.semesters import (
    LOOKAHEAD, SEMESTER_RE, next_semester, option_list, parse,
)
from app.services.percentiles import percentile_of

pytestmark = pytest.mark.unit


# UT-1.11
# percentile_of
# --------------------------------------------------------------------------- #
def test_ut_1_11_ranks_a_mark_within_its_population():
    assert percentile_of(3, [1, 2, 3]) == 100.0      # top of three
    assert percentile_of(2, [1, 2, 3]) == 66.7
    assert percentile_of(1, [1, 2, 3]) == 33.3       # bottom is NOT 0 — it is 1 of 3


def test_ut_1_11b_ties_share_a_percentile():
    """The half most likely to be reimplemented wrongly.

    Three learners tied at ranks 2, 3 and 4 all take the rank-3 percentile — the AVERAGE of the
    ranks they span. These are coarse rubric marks (phonics has 47 distinct values across 5,783
    learners), so ties are the common case, not an edge case.
    """
    assert percentile_of(5, [1, 5, 5, 5, 9]) == 60.0
    assert [percentile_of(m, [3, 3]) for m in (3, 3)] == [75.0, 75.0]


def test_ut_1_11c_an_unassessed_mark_has_no_percentile():
    """None in, None out — never 0. A 0 would say "bottom of the cohort", which is a claim about
    the learner; None says "we cannot tell", which is the truth."""
    assert percentile_of(None, [1, 2, 3]) is None


def test_ut_1_11d_an_empty_population_yields_none():
    """The first upload of a brand-new semester has nobody to rank against."""
    assert percentile_of(5, []) is None
    assert percentile_of(5, [None, None]) is None    # peers exist, but none sat this paper


def test_ut_1_11e_unassessed_peers_are_excluded_not_counted_as_zero():
    """A peer with no mark must not drag the population down.

    2,084 band-A learners have no writing mark at all; counting them as zeros would put anyone
    who did sit the paper at the top of a cohort that never took it.
    """
    assert percentile_of(5, [None, 5, None]) == percentile_of(5, [5])


# UT-1.12
# The agreement that keeps the two writers honest
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("population", [
    [1, 5, 5, 5, 9],            # a tie in the middle
    [1, 2, 3],                  # no ties
    [7],                        # one learner
    [3, 3],                     # everyone tied
    [0, 0, 0, 10],              # a tie at the bottom
    [2, 4, 6, 8, 10, 12],       # evenly spread
    [46, 46, 12, 0, 31, 31, 31],  # realistic phonics marks, repeated
])
def test_ut_1_12_matches_pandas_rank_pct_exactly(population):
    """UT-1.12: `percentile_of` == `(series.rank(pct=True) * 100).round(1)`, case for case.

    THE POINT OF THIS FILE. `dial_workbook.percentiles` writes `<feature>_pct` for ~22,892
    workbook sittings; `percentile_of` writes the same column for one uploaded sitting. The
    profile page cannot tell which writer produced a row, so if the rules differ a learner's
    percentile jumps when the source of their marks changes — with nothing on screen to explain
    it. Note this is pandas' `method="average"`, NOT SQL's `cume_dist()` (which seed.sql uses and
    which ranks ties at the top of their group).

    Skips without pandas, which is analysis-only and absent from the API's runtime deps — the
    same reason `percentile_of` had to be written in the first place.
    """
    pd = pytest.importorskip("pandas")

    series = pd.Series(population, dtype=float)
    expected = (series.rank(pct=True) * 100).round(1).tolist()

    assert [percentile_of(mark, population) for mark in population] == expected


# UT-1.13
# semesters
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("value", ["2026 Sem 1", "2026 Sem 2", "1999 Sem 1"])
def test_ut_1_13_accepts_the_canonical_shape(value):
    assert SEMESTER_RE.fullmatch(value)


@pytest.mark.parametrize("value", [
    "2026 Sem 3",       # there are two semesters
    "2026 sem 1",       # case matters: the sort is byte-wise
    "26 Sem 1",         # two-digit years break text ordering
    "2026 Sem",
    "Sem 1 2026",
    "2026-1",
    "",
])
def test_ut_1_13b_rejects_anything_that_would_sort_wrong(value):
    """A malformed semester does not error anywhere downstream — it just sorts somewhere
    arbitrary, so the sitting either never becomes "latest" or wrongly does. That silence is
    exactly why the shape is enforced at the boundary."""
    assert SEMESTER_RE.fullmatch(value) is None
    with pytest.raises(ValueError):
        parse(value)


def test_ut_1_13c_next_semester_walks_the_sequence_across_the_year():
    assert next_semester("2026 Sem 1") == "2026 Sem 2"
    assert next_semester("2026 Sem 2") == "2027 Sem 1"   # the boundary worth pinning


def test_ut_1_13d_the_option_list_extends_past_what_is_on_record():
    """The lookahead is what stops the list going stale.

    The options are built from stored sittings, so without it the first upload of a semester
    that has just begun would have nothing to select — the exact case that makes a dropdown
    worse than a text box.
    """
    options = option_list(["2025 Sem 1", "2025 Sem 2", "2026 Sem 1"])

    assert options[0] == "2027 Sem 1"                    # newest first, lookahead included
    assert options.count("2026 Sem 2") == 1              # generated, not duplicated
    assert "2025 Sem 1" in options
    assert len(options) == 3 + LOOKAHEAD


def test_ut_1_13e_the_default_option_is_the_newest_on_record():
    """Newest first means the form defaults to the semester an upload most likely belongs to."""
    assert option_list(["2024 Sem 1", "2026 Sem 1", "2025 Sem 2"])[LOOKAHEAD] == "2026 Sem 1"


def test_ut_1_13f_unparseable_rows_are_dropped_not_raised_on():
    """One bad legacy row must not 500 the endpoint that lists the options."""
    assert option_list(["2026 Sem 1", "whenever", None, ""]) == [
        "2027 Sem 1", "2026 Sem 2", "2026 Sem 1",
    ]


def test_ut_1_13g_an_empty_table_yields_an_empty_list():
    """A fresh project has no sittings. There is nothing to extend from, and inventing a
    "current" semester would need the academic calendar, which is recorded nowhere."""
    assert option_list([]) == []
