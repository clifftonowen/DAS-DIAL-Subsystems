"""A fuzzer for DAS D.I.A.L.

Written for the 50.003 robustness-testing deliverable, which asks us to *implement* a fuzzer
rather than only configure someone else's. The split that matters:

    fuzz/            THIS PACKAGE — the fuzzer. Runs for a wall-clock budget, keeps going past
                     the first failure, persists a corpus between runs.
    tests/fuzz/      the regression tier. Fast, deterministic pytest cases pinning what the
                     fuzzer found. Hypothesis lives there, not here.

The engine follows the Week 11 lecture's pipeline literally:

    Test Generator -> Input -> Program -> Test Oracle -> Pass / Fail

`strategies.py` is the generator, `targets/` wrap the program, `oracles.py` decides pass/fail.
"""
