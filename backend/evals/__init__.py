"""Offline evaluation harness for curriculum retrieval and activity generation.

Deliberately OUTSIDE app/: nothing here is imported by the API, and its dependencies live in
requirements-eval.txt so `pip install -r requirements.txt` (and therefore CI) never pulls ragas,
datasets or pandas. Run everything from backend/, e.g. `python -m evals.run_retrieval_eval`.

Named `evals` rather than `eval` to avoid a package that shadows the builtin in readers' heads.
"""
