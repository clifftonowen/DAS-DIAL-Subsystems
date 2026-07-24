"""CLI to test curriculum retrieval end-to-end (run from backend/).

    python -m scripts.query_curriculum "rhyming words activity" --band A1 --k 3
    python -m scripts.query_curriculum "expand the predicate" --concept action_predicate --full

Embeds the query with the active provider (Ollama nomic-embed-text, 768-dim) and ranks
curriculum_chunks via the match_curriculum RPC. Needs a live Supabase + a reachable embedder,
so the service is imported lazily inside the command (this module loads without those deps).
"""
from __future__ import annotations
import argparse
import textwrap

SNIPPET_CHARS = 160


def _snippet(text: str | None) -> str:
    """First line-ish of content_md, collapsed to one line and truncated."""
    flat = " ".join((text or "").split())
    return textwrap.shorten(flat, width=SNIPPET_CHARS, placeholder=" ...") if flat else "-"


def format_results(results: list[dict], full: bool) -> str:
    if not results:
        return ("no matches — corpus empty, filters too narrow, or Supabase unreachable "
                "(the service swallows errors and returns []).")
    lines: list[str] = []
    for i, r in enumerate(results, 1):
        title = r.get("activity_title") or "-"
        concept = r.get("concept") or "-"
        stage = r.get("stage") or "-"
        sim = r.get("similarity")
        sim_s = f"{sim:.3f}" if isinstance(sim, (int, float)) else "-"
        score = r.get("score")  # present only for hybrid results (RRF fused score)
        score_s = f"  score={score:.4f}" if isinstance(score, (int, float)) else ""
        page = r.get("page_start") or "?"
        src = r.get("source_file") or "?"
        lines.append(f"{i}. {title}  ({concept} / {stage})  sim={sim_s}{score_s}")
        lines.append(f"   {src} p.{page}")
        body = r.get("content_md") if full else _snippet(r.get("content_md"))
        lines.append(f"   {body}" if not full else textwrap.indent(body or "-", "   "))
        if r.get("answer_key"):
            lines.append(f"   [answer key: {_snippet(r['answer_key'])}]")
        lines.append("")
    return "\n".join(lines).rstrip()


def cmd_query(args: argparse.Namespace) -> int:
    # lazy: needs the embedding gateway + Supabase
    from app.services.curriculum_retrieval_service import CurriculumRetrievalService

    filters = {k: v for k, v in
               (("band", args.band), ("concept", args.concept), ("stage", args.stage)) if v}
    filt_s = f"  filters={filters}" if filters else ""
    mode = "vector-only" if args.vector_only else "hybrid"
    print(f'=== query: "{args.query}"  k={args.k}  [{mode}]{filt_s} ===\n')

    results = CurriculumRetrievalService().retrieve(
        args.query, band=args.band, concept=args.concept, stage=args.stage,
        k=args.k, vector_only=args.vector_only,
    )
    print(format_results(results, full=args.full))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="query_curriculum", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("query", help="the text to search for")
    p.add_argument("--band", help="filter: 'A1' | 'A2' | 'A3'")
    p.add_argument("--concept", help="filter: curriculum concept join key (e.g. action_predicate)")
    p.add_argument("--stage", help="filter: 'presentation' | 'practice' | 'production' | ...")
    p.add_argument("--k", type=int, default=3, help="number of chunks to return (default 3)")
    p.add_argument("--full", action="store_true", help="print full content_md, not a snippet")
    p.add_argument("--vector-only", action="store_true",
                   help="pure vector search (default is hybrid: vector + full-text, RRF)")
    p.set_defaults(func=cmd_query)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
