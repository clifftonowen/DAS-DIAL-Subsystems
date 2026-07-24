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
        args.query, band=args.band, concept=args.concept, stage=args.stage, k=args.k
    )

    # Guardrail: refuse before spending an LLM call when grounding is missing or weak.
    top_sim = chunks[0].get("similarity") if chunks else None
    if not chunks or not isinstance(top_sim, (int, float)) or top_sim < args.min_sim:
        best = f"{top_sim:.3f}" if isinstance(top_sim, (int, float)) else "none"
        print(f"{INSUFFICIENT_CONTEXT}\n  query/filters not covered by the corpus "
              f"(best similarity: {best}, gate: {args.min_sim}).\n"
              f"  Retrieved {len(chunks)} chunk(s). Loosen filters, lower --min-sim, or ingest "
              f"more curriculum.")
        return 2

    print(_grounding_header(chunks) + "\n")
    prompt = build_activity_prompt(chunks, params)
    activity = LLMApiClient().complete(prompt, system=SYSTEM_PROMPT)

    print("--- ACTIVITY ---")
    print(activity.strip() if activity else "(empty response from LLM)")
    # The model may still self-refuse even past the similarity gate.
    return 2 if activity and activity.lstrip().startswith(INSUFFICIENT_CONTEXT) else 0


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
