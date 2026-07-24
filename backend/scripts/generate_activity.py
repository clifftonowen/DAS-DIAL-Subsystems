"""CLI to generate a curriculum-grounded learning activity end-to-end (run from backend/).

    python -m scripts.generate_activity "rhyming words for A1" --band A1
    python -m scripts.generate_activity "expand the predicate" --concept action_predicate --k 4

Flow: retrieve curriculum chunks -> guardrail gate (refuse if grounding is thin) -> build the
guardrailed prompt -> LLM completion -> print the FULL learning activity. Needs a live Supabase +
a reachable LLM/embedder, so those imports are lazy inside the command.
"""
from __future__ import annotations
import argparse


def _grounding_header(chunks: list[dict]) -> str:
    lines = ["[grounding used]"]
    for i, c in enumerate(chunks, 1):
        title = c.get("activity_title") or "(untitled)"
        src = c.get("source_file") or "?"
        page = c.get("page_start") or "?"
        sim = c.get("similarity")
        sim_s = f"{sim:.3f}" if isinstance(sim, (int, float)) else "?"
        lines.append(f"  {i}. {title}  ({src} p.{page})  sim={sim_s}")
    return "\n".join(lines)


def _model_refused(text: str | None) -> bool:
    """True if the model self-refused with an INSUFFICIENT_CONTEXT signal on its first line.
    Tolerant of spacing/case/punctuation — models write 'INSUFFICIENT CONTEXT', bold it, or
    lowercase it, and almost never emit the exact underscore sentinel."""
    if not text or not text.strip():
        return False
    first_line = text.strip().splitlines()[0]
    norm = "".join(ch for ch in first_line.lower() if ch.isalnum())  # drop spaces/_/markdown
    return norm.startswith("insufficientcontext")


def cmd_generate(args: argparse.Namespace) -> int:
    # lazy: these need the embedding gateway + Supabase + the LLM
    from app.services.curriculum_retrieval_service import CurriculumRetrievalService
    from app.gateways.llm_client import LLMApiClient
    from app.prompts.activity_prompts import (
        SYSTEM_PROMPT, INSUFFICIENT_CONTEXT, build_activity_prompt,
    )

    params = {"band": args.band, "concept": args.concept, "stage": args.stage, "notes": args.query}
    filters = {k: v for k, v in
               (("band", args.band), ("concept", args.concept), ("stage", args.stage)) if v}
    print(f'=== generate: "{args.query}"  k={args.k}  min_sim={args.min_sim}'
          + (f'  filters={filters}' if filters else '') + ' ===\n')

    chunks = CurriculumRetrievalService().retrieve(
        args.query, band=args.band, concept=args.concept, stage=args.stage,
        k=args.k, vector_only=args.vector_only,
    )

    # Guardrail: refuse before spending an LLM call when grounding is missing or weak.
    # Hybrid orders by RRF score, so the top row isn't necessarily the most semantically similar
    # one — gate on the best semantic similarity across returned rows (keyword-only rows are None).
    sims = [c["similarity"] for c in chunks if isinstance(c.get("similarity"), (int, float))]
    top_sim = max(sims) if sims else None
    if not chunks or top_sim is None or top_sim < args.min_sim:
        best = f"{top_sim:.3f}" if isinstance(top_sim, (int, float)) else "none"
        print(f"{INSUFFICIENT_CONTEXT}\n  query/filters not covered by the corpus "
              f"(best similarity: {best}, gate: {args.min_sim}).\n"
              f"  Retrieved {len(chunks)} chunk(s). Loosen filters, lower --min-sim, or ingest "
              f"more curriculum.")
        return 2

    print(_grounding_header(chunks) + "\n")
    prompt = build_activity_prompt(chunks, params)
    activity = LLMApiClient().complete(
        prompt, system=SYSTEM_PROMPT, temperature=args.temperature, seed=args.seed,
    )

    # Second guardrail layer: the model may self-refuse past the similarity gate (e.g. an
    # off-topic request whose generic tokens sneak over the threshold). Detect it tolerantly —
    # models write "INSUFFICIENT CONTEXT", "insufficient_context", "**INSUFFICIENT_CONTEXT**",
    # etc., rarely the exact sentinel — and surface it as a refusal, not an activity.
    if _model_refused(activity):
        print("INSUFFICIENT_CONTEXT  (model refused — grounding does not cover the request)\n")
        print((activity or "").strip())
        return 2

    print("--- ACTIVITY ---")
    print(activity.strip() if activity else "(empty response from LLM)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="generate_activity", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("query", help="what activity to generate (also used as the retrieval query)")
    p.add_argument("--band", help="filter: 'A1' | 'A2' | 'A3'")
    p.add_argument("--concept", help="filter: curriculum concept join key (e.g. action_predicate)")
    p.add_argument("--stage", help="filter: 'presentation' | 'practice' | 'production' | ...")
    p.add_argument("--k", type=int, default=3, help="chunks to retrieve for grounding (default 3)")
    p.add_argument("--min-sim", type=float, default=None,
                   help="min top-chunk similarity to proceed (default: prompts.MIN_SIMILARITY)")
    p.add_argument("--vector-only", action="store_true",
                   help="pure vector retrieval (default is hybrid: vector + full-text, RRF)")
    p.add_argument("--temperature", type=float, default=None,
                   help="sampling temperature; 0 = reproducible (default: OLLAMA_TEMPERATURE / .env)")
    p.add_argument("--seed", type=int, default=None,
                   help="sampling seed; fixed = reproducible at temp 0 (default: OLLAMA_SEED / .env)")
    p.set_defaults(func=cmd_generate)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.min_sim is None:
        from app.prompts.activity_prompts import MIN_SIMILARITY
        args.min_sim = MIN_SIMILARITY
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
