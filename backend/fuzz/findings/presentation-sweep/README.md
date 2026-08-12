# Presentation sweep — 12 Aug 2026

The evidence behind the findings table in `docs/PM_Robustness_Testing.md`. Every defect reported
there has its JSON summary and its minimised reproducing input here.

## What was run

A six-minute coverage-guided sweep across all seven targets, budget split evenly:

```bash
cd backend
.venv/Scripts/python -m fuzz.runner --strategy coverage --target all --seconds 360 --seed 11
```

**`assessment_docx` is the exception** and its file is named `-mutation-` rather than `-coverage-`.
Its run in the sweep above still contained the `python-docx` false positive — the harness failing
to *write* a document containing control characters, several steps before the parser ran. That was
fixed (`_xml_safe` in `t_assessment_parser.py`) and the target re-run:

```bash
.venv/Scripts/python -m fuzz.runner --strategy mutation --target assessment_docx --seconds 60 --seed 5
```

The re-run is the honest artifact, so it is the one kept. It also produced a stronger result than
the original: it rediscovered the `float()` crash at `assessment_parser.py:104` through a **real
`.docx` round trip**, which is what makes that finding an upload a therapist could actually
perform rather than a curiosity about a function.

## Reading a finding

Each JSON carries `seed`, `execs`, `execs_per_second`, `rejected_pct`, `branch_arcs_reached`,
`measured_package`, and a `findings` array with the shortest input per bucket. Alongside, in
`inputs/`:

- `<signature>.bin` — the minimised input that reproduces it, byte for byte
- `<signature>.trace.txt` — the full traceback

Signatures are `<oracle>:<label>:<file>:<line>`, with `/` and `:` replaced by `_` in filenames. An
`invariant_*` file points at the *oracle* that failed in `fuzz/targets/`; a `crash_*` file points
at the line in `app/` where the program died, or at the framework frame when the failure happened
above our code (`crash_ValueError_starlette_responses.py_181`).

## Replaying one

Feed the `.bin` straight back to the target:

```bash
cd backend
.venv/Scripts/python -c "
from fuzz.targets import get
data = open('fuzz/findings/presentation-sweep/inputs/crash_ValueError_assessment_parser.py_104.bin','rb').read()
get('assessment_text').run(data)
"
```

It should raise. Whole campaigns replay from their recorded `seed`.

## Note on the numbers

`execs_per_second` is fuzzer throughput, not a load-test result — these are in-process calls with
every external boundary stubbed. It says how much of the input space the campaign covered, nothing
about how the deployed service performs under traffic.
