# The fuzzer

Robustness testing for DAS D.I.A.L. A fuzzer generates inputs nobody wrote by hand, feeds them to
the program, and checks the result against an oracle. It runs to a wall-clock budget rather than a
fixed number of cases, so the same harness serves a 30-second smoke check and a 24-hour campaign.

This is our own code, not a library wrapper. `coverage.py` is the only dependency and it arrives
free with `pytest-cov`.

## Running it

From `backend/`:

```bash
# smoke: every target, five minutes, split evenly
.venv/Scripts/python -m fuzz.runner --strategy coverage --target all --seconds 300

# one target
.venv/Scripts/python -m fuzz.runner --strategy mutation --target semesters --seconds 30

# a long campaign, replayable because the seed is fixed
.venv/Scripts/python -m fuzz.runner --strategy coverage --target all --hours 24 --seed 20260812 --quiet
```

Exit code `0` clean, `1` findings, `2` the engine itself failed on some target. Artifacts land in
`fuzz/findings/`: one JSON summary per target per run, plus the shortest reproducing input and its
traceback under `findings/inputs/`.

| Flag | Meaning |
|---|---|
| `--strategy` | `random`, `mutation`, `grammar`, `coverage` |
| `--target` | a target name, or `all` |
| `--seconds` / `--hours` | wall-clock budget, split evenly across targets |
| `--seed` | RNG seed. Omitted means time-based, and it is printed so any run can be replayed |
| `--hang-ms` | an input taking at least this long is reported as a hang (default 1000) |
| `--quiet` | suppress the ten-second progress line |

## The four strategies

From the Week 11 taxonomy. Each is a different answer to "where does the next input come from".

| Strategy | How it generates | Cost |
|---|---|---|
| `random` | uniform bytes | trivial to write, rejected early by any real validation |
| `mutation` | AFL-style havoc stacking on a corpus seed: flip, insert, delete, duplicate, repeat, swap, truncate, splice | needs good seeds |
| `grammar` | expands a BNF for the target's input language | reaches past validation reliably, but the grammar is work |
| `coverage` | mutation, plus a selection rule that keeps what explored new code | best coverage, slowest per input |

`coverage` is not a fifth generator. It is `mutation` wrapped in the feedback loop below, which is
why both map to the same class in `runner.STRATEGIES`.

## The feedback loop

Generate → execute → collect feedback → generate, with `coverage.py` branch arcs as the fitness
signal. This is the genetic-algorithm framing from the lecture: the suite is the population,
branch arcs reached are the fitness, and a generation that reaches arcs no earlier generation
reached has its contributing inputs promoted into the corpus. Everything else is discarded.

**The unit of selection is a suite, not an input, and that is a measurement not a preference.**
Tracing is not free, and granularity changes the answer by three orders of magnitude:

| Granularity | Cost per input |
|---|---|
| no coverage | 6.4 µs |
| per input | 8578 µs (1344×) |
| per 100-input suite | 98.1 µs (15.4×) |
| per 1000-input suite | 22.1 µs (3.5×) |
| per 3000-input suite | 18.5 µs (2.9×) |

At 1344× a 24-hour guided campaign would execute fewer inputs than a one-minute unguided one. So
the suite is scored, and only when a suite wins does the expensive per-input attribution pass run
to find which of its inputs deserve the credit. Cheap screen, expensive confirm.

Promoting the whole winning generation was the first implementation and it was wrong: 1000 inputs
went in at once, the corpus filled with near-duplicates, the rejection rate climbed to 99.8% and
the guided run found *fewer* defects than plain mutation. Corpus quality beats corpus size.

## The oracles

A fuzzer with no oracle can only find crashes. Naming them is what lets the report say *how* a
wrong answer was recognised.

| Oracle | Fires when | Example |
|---|---|---|
| CRASH | an exception escaped that the caller is not documented to handle | `float("1.2.3")` in the assessment parser |
| HANG | one input exceeded the wall-clock threshold | the quadratic email regex in `share_service` |
| INVARIANT | a property of the output is violated | `normalise_traits` returned a value outside `TRAITS` |
| ROUNDTRIP | `format(parse(s)) != s` | `'0922 Sem 1'` reformats as `'922 Sem 1'` |
| DIFFERENTIAL | two implementations of one rule disagree | `percentile_of` vs `dial_workbook.percentiles` |

`allowed` on each target is the contract being tested: the exceptions the caller is *documented* to
handle. For the assessment parser that list comes straight from the router (`InvalidFormatError` →
400, `ParseError` → 422), so anything else escaping is by construction an unhandled 500. The oracle
is derived from the production code, not guessed.

## The targets

| Target | Unit under test | Oracles | Measured |
|---|---|---|---|
| `semesters` | `app/ingestion/semesters.py` | crash, hang, invariant, roundtrip | `app.ingestion` |
| `normalise` | `app/ingestion/normalise.py` | crash, hang, invariant | `app.ingestion` |
| `assessment_text` | `parse_assessment_report`, text path | crash, hang, invariant | `app.ingestion` |
| `assessment_docx` | the same via a real `.docx` round trip | crash, hang, invariant | `app.ingestion` |
| `parse_verdict` | `app/prompts/activity_prompts.py` | crash, hang, invariant | `app.prompts` |
| `percentiles` | `app/services/percentiles.py` | crash, hang, invariant, differential | `app.services` |
| `http_api` | every HTTP endpoint, in process | crash, hang, invariant | `app` |

`measured` must name the package the unit actually lives in. Getting it wrong fails silently in the
worst way: coverage collects nothing, no generation ever looks like it found new arcs, and the
guided strategy quietly degrades to plain mutation while still calling itself guided. The runner
prints a warning if a campaign ends with zero arcs.

## Adding a target

Subclass `Target`, declare the contract, register it, and add it to `fuzz/targets/__init__.py`.

```python
@register
class MyTarget(Target):
    name = "my_target"
    allowed = (ValueError,)       # what the caller is documented to handle
    oracles = ("crash", "invariant")
    measured = "app.services"     # the package your unit lives in
    max_size = 8192

    def seeds(self) -> list[bytes]:
        return [b"a realistic input"]

    def run(self, data: bytes) -> None:
        result = my_function(as_text(data))
        invariant(result is not None, "my_function returned None")
```

Write oracles from the function's own docstring, and **do not reimplement the function to check
it** — a second copy of the logic agrees with the first copy's bugs. Prefer properties that must
hold regardless of implementation: idempotence, ordering, range, round trips.

### If your target touches anything outside this process, stub it

`http_api` stubs auth, Supabase, the LLM and SMTP, and calls `_assert_hermetic()` at import so the
campaign refuses to start if any of them is live.

That guard exists because we got it wrong. The first smoke run of `http_api` relayed four real
emails through Gmail before anyone noticed: `.env` has `EMAIL_ENABLED=True` and a real `SMTP_HOST`,
`POST /share` took the delivery branch, and the fuzzer had mutated `therapist@example.com` into
addresses like `tist@eherapxample.com`. Thirty seconds sent four messages. Eight hours would have
sent tens of thousands. **Enumerate every outbound boundary before you fuzz an endpoint** — the one
that gets missed is the one nobody thinks of as a boundary.

## Known limitations

Stated here rather than papered over.

- **Hangs are detected after the fact.** A pure-Python fuzzer cannot interrupt a regex mid-backtrack:
  `signal.alarm` does not exist on Windows, and CPython will not deliver a signal to a thread stuck
  inside the regex engine. Inputs are timed after they return, and the worst case is bounded by
  capping input size instead.
- **No shrinker.** We keep the shortest input seen per bucket, which is the poor relation of what
  Hypothesis does properly.
- **Suite-level coverage attributes credit coarsely.** Justified above, but it is still coarser
  than the per-input feedback AFL gets from compiler instrumentation.
- **Bucketing can still split or merge.** The signature is (oracle kind, exception type, deepest
  frame in `app/`, falling back to the framework frame and then to the target). One defect reachable
  by two code paths appears twice.

## Why not an off-the-shelf fuzzer

| Tool | Why not |
|---|---|
| AFL, libFuzzer, OSS-Fuzz, UTOPIA | all instrument C/C++. The prior art this imitates, not usable on a Python service. |
| Atheris (libFuzzer for Python) | the natural choice, and unavailable: no Windows wheel for 3.11. `pip install --dry-run --only-binary :all: atheris` returns "no matching distribution". |
| Hypothesis | property-based testing, not fuzzing: no coverage feedback and no wall-clock campaign. A good fit for a regression tier that replays these findings, which is not built yet. |
| Schemathesis | would fuzz `/openapi.json` cheaply, but gets no coverage feedback and cannot reach the pure functions that hold most of the logic. |
| JMeter, Locust | load testing. Different property, different tool. |

The brief asks for a fuzzer we implement in any language or platform, able to run over a very long
period. That is this.
