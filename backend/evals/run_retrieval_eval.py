"""Retrieval-only evaluation (run from backend/). No generation, no LLM judge.

    python -m evals.run_retrieval_eval --provider ollama --column embedding
    python -m evals.run_retrieval_eval --provider gemini --column embedding_alt
    python -m evals.run_retrieval_eval --provider gemini --column embedding_alt --vector-only

WHY DETERMINISTIC METRICS. This is the number two people compare across machines, so it must not
move for any reason other than the embedding model. Everything here is arithmetic over ranked
ids — recall, precision, MRR, nDCG, hit-rate — with no LLM anywhere in the path. An LLM-judged
metric (RAGAS context precision) varies run to run and would make a cross-machine comparison
meaningless; that lives in run_ragas.py instead.

COMPARING TWO RUNS. Two result files are comparable only if `golden.digest` matches AND the
document text was identical, which is why re-embedding goes through scripts/reembed_curriculum.py
(it replays the stored embed_text rather than re-parsing PDFs). The digest is written into every
result file; check it before believing any A/B.

This talks to the repository directly rather than through CurriculumRetrievalService, on purpose:
the service swallows exceptions and returns [], which in an evaluation would silently report a
broken RPC or an unreachable embedder as "recall 0.00" — a wrong answer that looks like a result.
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib
import statistics
import time

RESULTS_DIR = pathlib.Path(__file__).with_name("results")


# ── metrics ───────────────────────────────────────────────────────────────
def _dcg(gains: list[int]) -> float:
    return sum(g / math.log2(i + 2) for i, g in enumerate(gains))


def score_case(retrieved: list[tuple[str, str]], relevant: set[tuple[str, str]], k: int) -> dict:
    """Binary-relevance IR metrics for one ranked result list."""
    top = retrieved[:k]
    gains = [1 if key in relevant else 0 for key in top]
    hits = sum(gains)

    rank = next((i + 1 for i, g in enumerate(gains) if g), None)
    ideal = _dcg([1] * min(len(relevant), k))

    return {
        # recall is capped at k: with k=3 and 4 relevant chunks, perfect retrieval scores 0.75.
        # Reported as-is rather than normalised, because the pipeline really does only pass k
        # chunks to the model — the ceiling is a property of the system, not of the metric.
        "recall": hits / len(relevant) if relevant else None,
        "precision": hits / len(top) if top else 0.0,
        "hit": 1.0 if hits else 0.0,
        "mrr": 1.0 / rank if rank else 0.0,
        "ndcg": (_dcg(gains) / ideal) if ideal else None,
        "n_retrieved": len(top),
        "n_relevant": len(relevant),
        "first_hit_rank": rank,
    }


def _mean(values: list[float | None]) -> float | None:
    real = [v for v in values if isinstance(v, (int, float))]
    return sum(real) / len(real) if real else None


# ── run ───────────────────────────────────────────────────────────────────
def cmd_eval(args: argparse.Namespace) -> int:
    from app.core.config import settings
    from app.gateways.llm_client import LLMApiClient
    from app.prompts.activity_prompts import top_similarity
    from app.repositories.curriculum_repository import CurriculumRepository
    from evals.golden import load_corpus, load_golden

    settings.embedding_provider = args.provider
    LLMApiClient.use_provider(None)          # drop the cached provider so the override takes
    llm = LLMApiClient()

    corpus = load_corpus()
    golden = load_golden(corpus=corpus)
    repo = CurriculumRepository()
    use_alt = args.column != "embedding"
    mode = "vector-only" if args.vector_only else "hybrid"

    header = {
        "provider": args.provider,
        "embedding_model": llm.embedding_model,
        "embed_dim": llm.embed_dim,
        "column": args.column,
        "k": args.k,
        "mode": mode,
        "golden_digest": golden.digest,
        "golden_cases": len(golden.cases),
        "corpus_chunks": len(corpus),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    print("=== retrieval eval ===")
    for key, value in header.items():
        print(f"  {key:>16}: {value}")
    print()

    per_case, junk_sims, real_sims = [], [], []
    for case in golden.cases:
        vector = llm.embed(case.query, is_query=True)
        rows = _retrieve(repo, vector, case, args, use_alt)

        retrieved = [(str(r.get("source_file")), str(r.get("page_start"))) for r in rows]
        best = top_similarity(rows)
        record = {"id": case.id, "kind": case.kind, "top_similarity": best,
                  "retrieved": retrieved}

        if case.expects_hits:
            record.update(score_case(retrieved, set(case.relevant), args.k))
            real_sims.append(best)
            flag = "" if record["hit"] else "   <-- MISS"
            print(f"  {case.id:<28} recall={_f(record['recall'])} ndcg={_f(record['ndcg'])} "
                  f"mrr={_f(record['mrr'])} sim={_f(best)}{flag}")
        else:
            # Nothing is "correct" to retrieve; what matters is how confident the top hit looks,
            # because that number is what the similarity gate has to sit above.
            record["leaked"] = len(retrieved)
            junk_sims.append(best)
            print(f"  {case.id:<28} [{case.kind}] returned={len(retrieved)} sim={_f(best)}")
        per_case.append(record)

    scored = [r for r in per_case if r.get("n_relevant")]
    summary = {
        f"recall@{args.k}": _mean([r["recall"] for r in scored]),
        f"precision@{args.k}": _mean([r["precision"] for r in scored]),
        f"hit_rate@{args.k}": _mean([r["hit"] for r in scored]),
        "mrr": _mean([r["mrr"] for r in scored]),
        f"ndcg@{args.k}": _mean([r["ndcg"] for r in scored]),
        "n_scored_cases": len(scored),
    }
    gate = _gate_summary(real_sims, junk_sims)

    print("\n--- summary ---")
    for key, value in summary.items():
        print(f"  {key:>16}: {_f(value) if isinstance(value, float) else value}")
    print("\n--- gate separation (feeds scripts/calibrate_gate.py) ---")
    for key, value in gate.items():
        print(f"  {key:>16}: {_f(value) if isinstance(value, float) else value}")

    out = _write(header, summary, gate, per_case, args.out)
    print(f"\nwrote {out}")
    return 0


def _retrieve(repo, vector, case, args, use_alt: bool) -> list[dict]:
    if args.vector_only:
        return repo.match_curriculum(
            vector, band=case.band, band_group=case.band_group,
            concept=case.concept, stage=case.stage, match_count=args.k, use_alt=use_alt,
        )
    return repo.hybrid_match_curriculum(
        vector, case.query, band=case.band, band_group=case.band_group,
        concept=case.concept, stage=case.stage, match_count=args.k, use_alt=use_alt,
    )


def _gate_summary(real: list, junk: list) -> dict:
    real = sorted(v for v in real if isinstance(v, (int, float)))
    junk = sorted(v for v in junk if isinstance(v, (int, float)))
    if not real or not junk:
        return {"note": "not enough scored cases on one side to measure separation"}
    return {
        "real_min": real[0],
        "real_p05": real[max(0, int(len(real) * 0.05))],
        "real_median": statistics.median(real),
        "junk_max": junk[-1],
        "junk_median": statistics.median(junk),
        # Positive => a threshold exists that admits every real query and refuses every junk one.
        # Negative => the two overlap and NO single threshold separates them; report that rather
        # than splitting the difference, because a gate in the overlap refuses valid requests.
        "window": real[0] - junk[-1],
    }


def _f(value) -> str:
    return f"{value:.4f}" if isinstance(value, (int, float)) else "  -   "


def _write(header, summary, gate, per_case, out: str | None) -> pathlib.Path:
    RESULTS_DIR.mkdir(exist_ok=True)
    name = out or (f"retrieval_{header['provider']}_{header['embedding_model']}"
                   f"_{header['mode']}_k{header['k']}.json".replace(":", "-").replace("/", "-"))
    path = RESULTS_DIR / name
    path.write_text(json.dumps(
        {"header": header, "summary": summary, "gate": gate, "cases": per_case},
        indent=2, ensure_ascii=False,
    ), encoding="utf-8")
    return path


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="run_retrieval_eval", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--provider", default="gemini", choices=("gemini", "ollama", "openai"),
                   help="embedding provider for the QUERY side (default: gemini)")
    p.add_argument("--column", default="embedding_alt", choices=("embedding", "embedding_alt"),
                   help="which stored vectors to rank against. MUST match --provider, or you are "
                        "comparing one model's queries to another model's documents")
    p.add_argument("--k", type=int, default=3, help="chunks retrieved per query (default 3, "
                                                    "matching GenerationParams.k)")
    p.add_argument("--vector-only", action="store_true",
                   help="pure vector ranking instead of hybrid RRF (isolates the embedder)")
    p.add_argument("--out", help="result filename inside evals/results/ (default: derived)")
    p.set_defaults(func=cmd_eval)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
