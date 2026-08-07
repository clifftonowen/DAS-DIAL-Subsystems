"""Derive MIN_SIMILARITY for an embedding model from measured scores (run from backend/).

    python -m scripts.calibrate_gate --provider gemini --column embedding_alt
    python -m scripts.calibrate_gate --provider ollama --column embedding

WHY THIS IS NOT OPTIONAL. `MIN_SIMILARITY` refuses a request before spending an LLM call when the
best retrieved chunk is too weak to ground an activity. The number is meaningful only relative to
one embedding model's score band: nomic-embed-text puts junk near 0.42 and real matches at 0.58+,
so 0.50 sits in the gap. Another model has a different band — often a much higher and narrower
one — and carrying 0.50 across would not fail loudly, it would just start admitting junk or
refusing valid requests. Every embedding change needs this re-run.

The measurement is simply: score every in-domain golden query, score every deliberately
out-of-domain one, and look at whether the two clouds separate. The recommendation is the midpoint
of the gap. If they OVERLAP there is no safe threshold, and this says so rather than picking one.
"""
from __future__ import annotations

import argparse
import statistics

# Sit the gate at the midpoint of the gap rather than hard against the junk ceiling: both clouds
# are sampled from a handful of queries, so the true edges are wider than what we measured.
MIDPOINT = 0.5


def cmd_calibrate(args: argparse.Namespace) -> int:
    from app.core.config import settings
    from app.gateways.llm_client import LLMApiClient
    from app.prompts.activity_prompts import top_similarity
    from app.repositories.curriculum_repository import CurriculumRepository
    from evals.golden import load_corpus, load_golden

    settings.embedding_provider = args.provider
    LLMApiClient.use_provider(None)
    llm = LLMApiClient()

    corpus = load_corpus()
    golden = load_golden(corpus=corpus)
    repo = CurriculumRepository()
    use_alt = args.column != "embedding"

    print(f"=== gate calibration  provider={args.provider}  model={llm.embedding_model}  "
          f"column={args.column} ===\n")

    real: list[tuple[str, float]] = []
    junk: list[tuple[str, float]] = []
    for case in golden.cases:
        vector = llm.embed(case.query, is_query=True)
        rows = repo.hybrid_match_curriculum(
            vector, case.query, band=case.band, band_group=case.band_group,
            concept=case.concept, stage=case.stage, match_count=args.k, use_alt=use_alt,
        )
        best = top_similarity(rows)
        if best is None:
            print(f"  {case.id:<28} no similarity returned (keyword-only or empty) — skipped")
            continue
        (real if case.expects_hits else junk).append((case.id, best))

    if not real or not junk:
        print("\nnot enough cases on both sides to calibrate — need in_domain AND out_of_domain.")
        return 2

    _report("IN-DOMAIN (must PASS the gate)", real)
    _report("OUT-OF-DOMAIN (must be REFUSED)", junk)

    real_min = min(v for _, v in real)
    junk_max = max(v for _, v in junk)
    worst_real = min(real, key=lambda kv: kv[1])
    worst_junk = max(junk, key=lambda kv: kv[1])

    print(f"\nlowest real match : {real_min:.4f}  ({worst_real[0]})")
    print(f"highest junk match: {junk_max:.4f}  ({worst_junk[0]})")

    if real_min > junk_max:
        recommended = junk_max + (real_min - junk_max) * MIDPOINT
        print(f"\nCLEAN SEPARATION — gap {real_min - junk_max:.4f}")
        print(f"\n  RECOMMENDED  MIN_SIMILARITY={recommended:.2f}")
        print(f"\nSet it in .env as MIN_SIMILARITY={recommended:.2f} (config.py reads it; "
              f"activity_prompts re-exports it).")
        return 0

    overlap = [c for c, v in real if v <= junk_max]
    print(f"\nNO CLEAN SEPARATION — the clouds overlap by {junk_max - real_min:.4f}.")
    print(f"  {len(overlap)} in-domain case(s) score at or below the junk ceiling: "
          f"{', '.join(overlap)}")
    print("\nDo NOT split the difference: any threshold in the overlap refuses valid requests.")
    print("Either the labels for those cases are wrong, or this model cannot separate them —")
    print("check the cases above by hand before trusting either conclusion.")
    return 1


def _report(label: str, scored: list[tuple[str, float]]) -> None:
    values = sorted(v for _, v in scored)
    print(f"{label}  n={len(values)}")
    print(f"    min={values[0]:.4f}  median={statistics.median(values):.4f}  max={values[-1]:.4f}")
    for case_id, value in sorted(scored, key=lambda kv: kv[1]):
        print(f"      {value:.4f}  {case_id}")
    print()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="calibrate_gate", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--provider", default="gemini", choices=("gemini", "ollama", "openai"))
    p.add_argument("--column", default="embedding_alt", choices=("embedding", "embedding_alt"),
                   help="must match --provider — see run_retrieval_eval")
    p.add_argument("--k", type=int, default=3, help="chunks retrieved per query (default 3)")
    p.set_defaults(func=cmd_calibrate)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
