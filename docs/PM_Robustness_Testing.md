# Robustness Testing

*DAS D.I.A.L. — 50.003 Elements of Software Construction*

The brief asks four things of robustness testing: find fuzzing targets in the project, implement a
fuzzer in any language or platform, have it able to run over a very long period (24 hours), and
have it ready by the final presentation. This document answers **what was tested, what process was
followed, what tools were used, and what was found**.

The fuzzer lives in `backend/fuzz/`. `backend/fuzz/README.md` is the engineering guide: how to run
it, how to add a target, and the design rationale. This document is the result.

---

## 1. What a fuzzer is, and why one is worth building here

Our other four test tiers (unit, integration, e2e, system — 419 hermetic tests) all share a
limitation: every input in them was written by a person who was thinking about the code at the
time. They check the cases we thought of. A fuzzer generates inputs nobody thought of, runs them in
bulk, and checks the outcome against an oracle.

That is a good fit for this project specifically. D.I.A.L. ingests documents produced outside our
control — assessment reports as PDF and DOCX — and consumes text produced by a language model.
Neither is a source we can constrain by asking nicely, and both feed code paths that write to a
learner's permanent record.

---

## 2. Tools considered

The brief permits any language or platform and suggests JMeter, Hypothesis and fast-check "if time
permitted". The lecture (Week 11B) names AFL, libFuzzer, OSS-Fuzz and UTOPIA.

| Tool | Decision |
|---|---|
| **Our own fuzzer** | **Built.** ~2,300 lines in `backend/fuzz/`. Implements all four strategies from the Week 11 taxonomy with coverage feedback. |
| **`coverage.py`** | **Used**, as the feedback signal. Already a `pytest-cov` dependency, so the feedback loop cost no new dependency. |
| Atheris (libFuzzer for Python) | **Rejected — unavailable.** The natural choice, and there is no Windows wheel for Python 3.11. Verified: `pip install --dry-run --only-binary :all: atheris` returns "no matching distribution found". |
| AFL, libFuzzer, OSS-Fuzz, UTOPIA | **Rejected — wrong language.** All four instrument C/C++ at compile time. They are the prior art our feedback loop imitates in pure Python, not tools we could point at a Python service. |
| Hypothesis | **Not used yet.** Property-based testing, not fuzzing: no coverage feedback, no wall-clock campaign. It is the right tool for a *regression tier* that replays our findings, which is future work (§7). |
| Schemathesis | **Rejected — insufficient reach.** Would fuzz `/openapi.json` cheaply, but gets no coverage feedback, and most of the logic worth attacking is in pure functions no HTTP schema describes. |
| JMeter, Locust | **Out of scope.** Load testing measures behaviour under volume; fuzzing measures behaviour under *malformed* input. Different property. |

**The main engineering challenge was that the obvious tool did not exist for our platform.** Atheris
is how you would normally do this in Python, and the Windows gap meant building the feedback loop
ourselves on top of `coverage.py`. That constraint produced the measurement in §4, which is the
most interesting engineering result in this document.

---

## 3. Fuzzing targets

Targets were chosen on three criteria: the input crosses a trust boundary, the unit has a stated
contract an oracle can be written from, and it is cheap to run in isolation.

| Target | Unit under test | Why |
|---|---|---|
| `assessment_text` | `parse_assessment_report`, text path | UC1's upload. Parses a document we did not create. Named as a fuzz target in the PM3 test plan. |
| `assessment_docx` | the same, via a real `.docx` round trip | The extension check is the only gate; everything past it trusts the file. |
| `normalise` | `app/ingestion/normalise.py` | 136 lines of pure string transforms whose docstrings state total functions. Named in the PM3 test plan. |
| `semesters` | `app/ingestion/semesters.py` | `'2026 Sem 1'` is half the natural key of `learner_sittings` and is sorted **as text**, so a malformed one is silently misfiled rather than rejected. |
| `parse_verdict` | `app/prompts/activity_prompts.py` | The only place we parse LLM output. Documented to *fail closed*, which is a security property worth attacking. |
| `percentiles` | `app/services/percentiles.py` | Has an independent second implementation (`dial_workbook.percentiles`) documented to agree exactly — a true differential oracle. |
| `http_api` | every HTTP endpoint, in process | The external attack surface. Tests the "security" property the brief asks for directly. |

---

## 4. Process

### 4.1 The loop

Generate → execute → check the oracle → record → repeat, to a wall-clock budget rather than a fixed
case count. The campaign **continues past the first failure**, bucketing crashes by signature, so
one run reports "N distinct defects" rather than stopping on the first one.

### 4.2 Four generation strategies

| Strategy | How it generates |
|---|---|
| Random | uniform bytes. Minimal setup; rejected early by real validation. |
| Mutation | AFL-style havoc stacking on a corpus of valid seeds: flip, insert, delete, duplicate, repeat, swap, truncate, splice. |
| Grammar | expands a BNF for the target's input language, so generated inputs are structurally valid. |
| Feedback-guided | mutation plus a coverage-based selection rule (below). |

### 4.3 Feedback guidance, and the measurement that shaped it

The feedback strategy is the genetic algorithm from the lecture: the **suite is the population**,
**branch arcs reached are the fitness**, and a generation reaching arcs no earlier generation
reached has its contributing inputs promoted into the corpus. Everything else is discarded —
survival of the fittest.

The design decision worth reporting is the *granularity* of the coverage measurement, because it
changes throughput by three orders of magnitude:

| Tracing granularity | Cost per input | Slowdown |
|---|---|---|
| none | 6.4 µs | 1× |
| per input | 8578 µs | **1344×** |
| per 100-input suite | 98.1 µs | 15.4× |
| per 1000-input suite | 22.1 µs | 3.5× |
| per 3000-input suite | 18.5 µs | 2.9× |

Per-input feedback — what AFL gets free from compiler instrumentation — is unusable in Python: at
1344×, a 24-hour guided campaign would execute fewer inputs than a one-minute unguided one. So the
unit of selection is a **suite**, and the expensive per-input attribution pass runs only after a
suite has already proved it found something. Cheap screen, expensive confirm.

**A negative result worth recording:** promoting the entire winning generation was the first
implementation and it was *worse than no guidance at all*. A thousand inputs entered the corpus at
once, it filled with near-duplicates, the rejection rate climbed to 99.8%, and the guided campaign
found fewer defects than plain mutation. Corpus quality beats corpus size.

### 4.4 Five oracles

A fuzzer with no oracle can only detect crashes — and a crash is the *least* dangerous defect,
because it is loud. The wrong-answer cases are the ones that reach a therapist.

| Oracle | Fires when |
|---|---|
| CRASH | an exception escaped that the caller is not documented to handle |
| HANG | one input exceeded a wall-clock threshold |
| INVARIANT | a property of the output is violated (range, subset, non-null) |
| ROUNDTRIP | `format(parse(s)) != s` |
| DIFFERENTIAL | two implementations of the same rule disagree |

Oracles are derived from the code, not invented. Each target's `allowed` list — the exceptions that
mean "correctly rejected" — is taken from the router that catches them. For the assessment parser
that is `InvalidFormatError → 400` and `ParseError → 422`, so **anything else escaping is by
construction an unhandled 500**.

### 4.5 Keeping the campaign honest

Three engineering problems had to be solved before the results could be trusted:

**Isolation.** The `http_api` target runs the real app in-process with four boundaries stubbed:
auth, Supabase, the LLM, and SMTP. The first smoke run relayed **four real emails through Gmail**
before this was noticed — `.env` has `EMAIL_ENABLED=True` with a live SMTP host, and the fuzzer had
mutated `therapist@example.com` into addresses like `tist@eherapxample.com`. Thirty seconds sent
four; eight hours would have sent tens of thousands. The target now calls `_assert_hermetic()` at
import and **refuses to start** if any boundary is live. The lesson generalises: enumerate every
outbound boundary before fuzzing an endpoint, because the one you miss is the one you do not think
of as a boundary.

**False findings.** Four early "defects" were bugs in the fuzzer, not the program:

- httpx rejecting a control character in a URL *before sending* — fixed by percent-encoding, so
  the bytes reach the server where they can actually be judged;
- httpx refusing to serialise `Infinity` — fixed by encoding the body ourselves, which then found
  finding #8, a real one;
- an oracle that restated `model_refused`'s implementation instead of its contract, and so
  reported the function for doing exactly what its docstring promises;
- `python-docx` refusing to *write* a document containing control characters — the harness failing
  to build its own input, several steps before the parser ran.

All four were reported against our own filenames. **A finding that points at the harness is not a
finding**, and separating the two had to be done deliberately rather than assumed. It is also why
the defects in §5 are stated with confidence.

**Attribution.** One real 500 has no `app/` frame in its traceback at all — the app accepts
`Infinity` into a float field and then *starlette* fails to encode the response. The bucketing was
blaming our own call site, so it now falls back to the deepest framework frame.

**What the HTTP results do and do not cover.** Stubbing the database is what makes the campaign
fast and repeatable, and it also bounds the claim: `FakeSupabase` is an in-memory stand-in, so
findings below the repository layer — PostgREST filter semantics, constraint violations, the real
pgvector RPCs — are out of reach by construction. `http_api` tests the request path down to the
repository boundary. Everything past it is covered by the e2e tier against the real test project,
which is a different tier for a reason.

---

## 5. Findings

All reproducible from `backend/fuzz/findings/`, which holds the JSON summary per target plus the
minimised reproducing input and full traceback for every defect below. Seeds are recorded, so
campaigns replay exactly; `presentation-sweep/README.md` shows how to replay a single input.

### The campaign

Eight hours, all seven targets, coverage-guided, one fixed seed, run unattended overnight:

```bash
.venv/Scripts/python -m fuzz.runner --strategy coverage --target all --hours 8 --seed 20260812
```

| Target | Executions | Rate | Rejected | Branch arcs | Generations kept | Findings |
|---|---:|---:|---:|---:|---:|---:|
| `semesters` | 69,618,000 | 16,921/s | 99.8% | 26 | 1 / 69,619 | 3 |
| `parse_verdict` | 1,977,371 | 481/s | 0.0% | 44 | 2 / 1,978 | 2 |
| `percentiles` | 1,747,644 | 425/s | 0.0% | 22 | 2 / 1,748 | 1 |
| `normalise` | 666,807 | 162/s | 0.0% | 56 | 2 / 667 | 2 |
| `assessment_text` | 93,259 | 23/s | 76.5% | 23 | 2 / 94 | 4 |
| `http_api` | 62,609 | 15/s | 0.0% | 843 | 9 / 418 | 2 |
| `assessment_docx` | 51,685 | 13/s | 78.9% | 66 | 2 / 52 | 3 |
| **Total** | **74,217,375** | | | | | **17** |

Throughput spans **1,300×** between the fastest and slowest target, which matters for how the
budget should be spent (§7).

### The defects

| # | Target | Oracle | Defect | Impact |
|---|---|---|---|---|
| 1 | `assessment_text`, `assessment_docx` | CRASH | `float()` on the regex group `[\d.]+` raises on `'.'` (`assessment_parser.py:104`) | **Unhandled 500 on upload.** The router catches only `InvalidFormatError` / `ParseError`. Found by both targets, so it is reachable by uploading a real `.docx`, not only by calling the function. |
| 2 | `assessment_text`, `assessment_docx` | CRASH | `int()` on `\d+` exceeds CPython's 4300-digit limit (`assessment_parser.py:120`) | Unhandled 500. `\d` is Unicode-aware, so non-ASCII digits reach it too. |
| 3 | `normalise` | CRASH | the same 4300-digit limit in `extract_sequence_no` (`normalise.py:75`) | In a function whose docstring declares it total. |
| 4 | `assessment_text`, `assessment_docx` | INVARIANT | a task parses as `7 out of 1`; another as `9 out of 0` | Silently wrong data. `TaskResult` has no validator, so an impossible score persists to the learner's record with no error anywhere. |
| 5 | `semesters` | ROUNDTRIP | `'0226 Sem 2'` is accepted and reformatted as `'226 Sem 2'` | `int('0226')` drops the pad. The sitting is filed under a semester that is not the one submitted. |
| 6 | `semesters` | INVARIANT | `next_semester('9999 Sem 2') == '10000 Sem 1'`, which sorts *before* it | Text ordering is what `latest_for_learner` depends on. |
| 7 | `semesters` | INVARIANT | `option_list` emits `'10000 Sem 1'`, a value its own `SEMESTER_RE` rejects | The API offers a choice it would then refuse. |
| 8 | `http_api` | CRASH | `Infinity` accepted into a float field, then starlette cannot encode its own response (`starlette/responses.py:181`) | Unhandled 500. Pydantic v2 accepts `inf` / `nan` by default. |
| 9 | `http_api` | CRASH | an empty `assessment_date` passes the request model and raises `ValidationError` deeper in (`assessment_service.py:60`) | Unhandled 500. The request was accepted, then failed below the boundary. |
| 10 | `parse_verdict` | INVARIANT | `top_similarity` returns `True` where a float was promised | `isinstance(True, int)` is `True` in Python, so a bool similarity passes the numeric filter. A retrieval gate comparing it against `MIN_SIMILARITY` is comparing against `1.0`. |
| **11** | `parse_verdict` | CRASH | a deeply nested JSON payload raises `RecursionError`, which `parse_verdict` does not catch (`activity_prompts.py:218`) | **The fail-closed guarantee does not hold.** The function catches `JSONDecodeError` only; on this input it neither approves nor rejects, it throws. Reachable because the reviewer's reply is LLM output, the one input we cannot constrain. |
| **12** | `percentiles` | DIFFERENTIAL | `percentile_of(nan) = 100.0` where `dial_workbook.percentiles` gives `None` | **The two writers disagree.** pandas treats NaN as not-assessed; the hand-written twin compares `nan < mark` (always `False`), counts nobody below, and ranks it top of the cohort. A learner with a missing mark is shown at the 100th percentile. |
| 13 | `assessment_text`, `assessment_docx`, `normalise` | HANG | worst case **64 seconds** on a 4.4 KB input | The task regex `^([A-Za-z][A-Za-z\s]+?)\s+(\d+)\s+(\d+)\s*$` backtracks quadratically: `[A-Za-z\s]+?` is followed by `\s+` and both match whitespace. A denial of service on the upload path from a file a therapist could plausibly be sent. |

Thirteen rows, seventeen findings: rows 1–4 and 13 were each reported independently by more than
one target, which is the corroboration that made them worth trusting.

### What the long campaign bought

Findings **11** and **12** are the answer to "why run for eight hours rather than six minutes",
and they are the two most serious defects in the table.

- The `RecursionError` needs the repeat-span mutator to amplify a brace run into thousands of
  nesting levels. Its minimised reproducer is still 9,730 bytes. Nothing in the seed corpus
  resembles it and no short campaign reached it.
- The `percentiles` differential fired only after ~1.7 million populations. **The six-minute sweep
  reported this target as finding nothing**, and that report was wrong — not because the oracle was
  broken, but because the disagreement lives on one specific value the short run never generated.

The long campaign also *minimised* what the short one had already found: the `float()` crash went
from `'0.90.1'` to `'.'`, which is a better line in a report and a better regression test.

### The pattern

Ten of thirteen share one root cause: **validation happens after the boundary, not at it.**
Unguarded `int()` / `float()` casts on regex groups, exception handlers that name one exception
type where two can arrive, and request models with no constraints (`TaskResult` has no validator
at all; `GenerationParams.k` has no `ge` / `le`). The fix is the same everywhere — constrain the
model, guard the cast, widen the handler — which is a better outcome than thirteen unrelated bugs
would have been.

### The negative results

- **`GET /learners` survived.** It is the only endpoint with bounded query parameters
  (`page: ge=1`, `per_page: ge=1, le=100`) and it was included as a deliberate negative control.
  The fuzzer broke the endpoints that do not validate their inputs and failed to break the one
  that does, across 62,609 requests. That is a stronger argument for the fix than the list of
  failures alone.
- **`percentiles` agrees everywhere except NaN.** 1.7 million populations — heavy ties, unassessed
  learners, single-member and empty populations, values spanning the float range — produced exactly
  one disagreement, finding #12. The duplicate implementation the codebase worried about is
  correct on every real mark and wrong on the one value that means "no mark".

**A correction worth recording, because it is a lesson about fuzzing rather than about this code.**
The six-minute sweep reported `percentiles` as clean, and that was written up as a positive result:
"the two implementations agree exactly". The overnight campaign disproved it. A short campaign
finding nothing is not evidence that nothing is there — it is evidence that nothing was found, and
the two are only the same claim once the budget is large enough to justify the inference. This is
the concrete reason the brief asks for a fuzzer that can run for 24 hours, and we produced the
mistake ourselves before we produced the fix.

### Not yet fixed

The findings are the deliverable. Fixes and before/after evidence come next: every defect above has
a minimised reproducer stored, so the same campaign can be re-run against the corrected code and
the table regenerated. Findings #11 and #12 should be fixed first — both are wrong-answer defects
in code whose docstrings promise the opposite, and neither raises anything a user would see.

---

## 6. The long-run requirement

The brief asks for a fuzzer "able to run and generate tests over a very long period (e.g. 24
hours)". **An unattended 8-hour campaign has been run**, start to finish, with no supervision and
no intervention: 74.2 million executions across seven targets, all artifacts written, clean exit.
The numbers in §5 are its output, not an extrapolation.

Length is a flag (`--hours 24`), not a redesign, and four properties are what make an unattended
run trustworthy rather than merely long:

- **Replayable.** Every run prints and records its seed. Nothing in the table above is a
  once-observed event.
- **Incremental.** Artifacts are written per target as each finishes, so a campaign killed at hour
  six still yields six targets' evidence.
- **Fault-tolerant.** An engine failure in one target reports itself and moves on instead of
  aborting the sweep. Ctrl-C still writes what the current target found.
- **Encoding-safe.** Reproducers are arbitrary bytes, and printing one used to kill the process on
  a Windows console *after* its artifacts were written — losing every later target. Fixed.

Two of those were added because the first attempt at an overnight run exposed them, which is the
argument for doing a long run before relying on one.

The remaining gap to a full 24 hours is budget, not capability. What that budget should buy is
§7's first item: on the evidence above, another 16 hours split evenly would spend most of itself
re-confirming three known `semesters` defects at 16,921 execs/s.

---

## 7. Future work

- **Weight the budget by target speed.** The most valuable change, and the campaign quantified it.
  `--target all` splits the budget evenly, but measured throughput spans **1,300×**: `semesters`
  ran 69.6 million executions at 16,921/s while `assessment_docx` managed 51,685 at 13/s. An equal
  time slice therefore buys wildly unequal exploration — `semesters` spent 69 minutes re-confirming
  three defects it finds in the first second, and it kept **1 generation in 69,619**, meaning its
  corpus stopped improving almost immediately. Better signals to spend on: new arcs per minute, or
  simply stopping a target whose coverage has plateaued.
- **Regression tier.** Replay each finding's minimised input as a pytest case (`backend/tests/fuzz/`)
  so fixed defects stay fixed. Hypothesis is the right tool, and would let us honestly claim one of
  the brief's named tools.
- **CI job.** A 60-second smoke campaign per pull request.
- **Shrinking.** We keep the shortest input seen per bucket, which is why finding #11's reproducer
  is still 9,730 bytes — a real shrinker would cut it to the few dozen nested braces that actually
  matter.
- **Grammar coverage for `http_api`.** It reached 843 branch arcs, far more than any other target,
  and kept 9 generations in 418 — it was still finding new code when the budget ran out. It is the
  target most likely to repay more time.

---

## Appendix: reproducing this

```bash
cd backend
.venv/Scripts/python -m fuzz.runner --strategy coverage --target all --seconds 300
.venv/Scripts/python -m fuzz.runner --strategy coverage --target all --hours 24 --seed 20260812 --quiet
```

Artifacts in `backend/fuzz/findings/`. See `backend/fuzz/README.md` for the full guide.
