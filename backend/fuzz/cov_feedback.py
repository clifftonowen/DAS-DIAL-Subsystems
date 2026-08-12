"""Feedback-guided fuzzing, using `coverage.py` as the feedback signal.

This is the lecture's fourth strategy: Generate -> Execute -> Collect Feedback -> Generate. It is
what AFL and libFuzzer do with compiler instrumentation. We cannot use those (they instrument
C/C++, and Atheris, the Python binding to libFuzzer, has no Windows support), but `coverage.py`
is already installed as a `pytest-cov` dependency, so the feedback loop costs no new dependency.

THE MEASUREMENT THAT DICTATES THE DESIGN. Tracing is not free, and the granularity you trace at
changes the answer by three orders of magnitude. Measured on this machine against
`normalise_stage`:

    no coverage at all                     6.4 us/input
    coverage start/stop per input       8578.0 us/input   (1344x slower)
    coverage around a 100-input suite     98.1 us/input     (15.4x)
    coverage around a 1000-input suite     22.1 us/input      (3.5x)
    coverage around a 3000-input suite     18.5 us/input      (2.9x)

Per-input feedback is therefore unusable: at 1344x, a 24-hour guided campaign would execute fewer
inputs than a 1-minute unguided one. So the unit of selection is a SUITE, not an input, which is
also how the lecture frames the genetic-algorithm variant ("population = test suite"). The suite
is the thing that gets scored, kept, and evolved.
"""
from __future__ import annotations

import warnings
from pathlib import Path

import coverage
from coverage.exceptions import CoverageWarning

# Also filtered globally, not just inside `measure`'s context manager. The per-call
# `catch_warnings` block below does not actually suppress these in practice, and an overnight run
# starts a tracer thousands of times, so the two warnings coverage always emits here
# ("module-not-measured" for the pre-imported target modules, "no-data-collected" for the
# per-input attribution passes that touch nothing) would otherwise bury the progress lines.
warnings.filterwarnings("ignore", category=CoverageWarning)

#: Inputs per generation. Chosen from the table above: 1000 is where the tracing overhead falls
#: to ~3.5x, and going to 3000 buys only another 0.6x while making each generation's feedback
#: coarser (more inputs share the credit for any new arc found).
SUITE_SIZE = 1000

#: Default package to measure, as a MODULE name, not a path. Each target overrides it via
#: `Target.measured`; this constant is only the fallback for the ingestion targets that came first.
#:
#: `include=[<absolute windows path>*]` silently collects nothing - measured, 0 files and 0 arcs,
#: with only a "No data was collected" warning to show for it. `source=["app.ingestion"]` collects
#: correctly. The difference is that `include` patterns are matched against filenames coverage has
#: already decided to trace, so an unmatched pattern fails closed and looks exactly like "the code
#: never ran".
_MEASURED = "app.ingestion"


class ArcTracker:
    """Accumulates the set of branch arcs any generation has ever reached."""

    def __init__(self, measured: str = _MEASURED):
        self.measured = measured
        self.seen: set[tuple[str, int, int]] = set()

    def measure(self, run_suite) -> set[tuple[str, int, int]]:
        """Run `run_suite()` under a fresh tracer and return the arcs it covered.

        A fresh `Coverage` per generation rather than one long-lived object: we want THIS
        generation's arcs so a suite can be scored on its own merit, and accumulating into one
        object would make every generation after the first look like it found nothing new.
        """
        cov = coverage.Coverage(branch=True, data_file=None, source=[self.measured])
        with warnings.catch_warnings():
            # The target modules are imported before the tracer starts, so coverage warns that it
            # could not measure their module-level lines. Irrelevant here: we score the arcs
            # inside the functions we call, and those trace normally.
            warnings.simplefilter("ignore", CoverageWarning)
            cov.start()
            try:
                run_suite()
            finally:
                cov.stop()

        arcs: set[tuple[str, int, int]] = set()
        data = cov.get_data()
        for filename in data.measured_files():
            name = Path(filename).name
            for start, end in data.arcs(filename) or ():
                arcs.add((name, start, end))
        return arcs

    def new_arcs(self, arcs: set[tuple[str, int, int]]) -> int:
        """How many arcs this generation reached that no earlier generation did."""
        return len(arcs - self.seen)

    def attribute(self, suite, run_one, wanted, limit: int = 64) -> list:
        """Find which individual inputs of a winning generation reached `wanted`.

        WHY THIS EXISTS. Promoting a whole winning generation into the corpus was the first
        implementation and it was wrong: 1000 inputs went in at once, the corpus filled with
        near-duplicate junk, the rejection rate climbed to 99.8% and the campaign found FEWER
        defects than the unguided mutation run. Corpus quality matters more than corpus size.

        The cost is affordable precisely because winning generations are rare. Per-input tracing
        is ~8.5 ms, so attributing a 1000-input generation costs ~8.5 s; at the measured rate of
        roughly one winning generation in 400, that is a few seconds per campaign-hour. This is
        the cheap-screen / expensive-confirm pattern: suite-level to decide IF anything new was
        found, per-input only to decide WHICH input found it.
        """
        contributors = []
        for data in suite:
            if len(contributors) >= limit:
                break
            arcs = self.measure(lambda: run_one(data))
            if arcs & wanted:
                contributors.append(data)
        return contributors

    def absorb(self, arcs: set[tuple[str, int, int]]) -> None:
        self.seen |= arcs

    @property
    def total(self) -> int:
        return len(self.seen)
