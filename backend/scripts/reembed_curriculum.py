"""Re-embed the curriculum corpus in place, without the source PDFs (run from backend/).

    python -m scripts.reembed_curriculum --provider gemini --column embedding_alt --dry-run
    python -m scripts.reembed_curriculum --provider gemini --column embedding_alt
    python -m scripts.reembed_curriculum --provider ollama --column embedding --force

WHY THIS EXISTS RATHER THAN `ingest_curriculum run --all`. Ingestion re-parses from PDF, and the
PDFs are gitignored — on a fresh clone there is nothing to re-ingest FROM. But `embed_text` (the
exact string chunk_builder handed the embedder) is persisted on every row, so re-embedding from
the database reproduces the document side byte-for-byte. That byte-for-byte part is the whole
point: if two models are fed even slightly different text, the comparison measures the text, not
the models.

It is also an UPDATE rather than delete-then-insert, so chunk `id`s survive. A full re-ingest
regenerates them, which would quietly break any evaluation keyed on chunk identity.
"""
from __future__ import annotations

import argparse

# Writing the incumbent column destroys the vectors everything currently retrieves against, and
# on a shared database that includes other people's in-flight work. Needs --force, said out loud.
INCUMBENT = "embedding"


def cmd_reembed(args: argparse.Namespace) -> int:
    # lazy: needs Supabase + a reachable embedder (this module imports without either)
    from app.core.config import settings
    from app.gateways.llm_client import LLMApiClient
    from app.repositories.curriculum_repository import CurriculumRepository

    if args.column == INCUMBENT and not args.force:
        print(f"refusing to overwrite `{INCUMBENT}` without --force.\n"
              f"  That column is what the live app and any baseline measurement retrieve against,\n"
              f"  and on a shared database someone else may be mid-evaluation against it.\n"
              f"  Write the challenger to --column embedding_alt instead, or pass --force.")
        return 2

    settings.embedding_provider = args.provider
    LLMApiClient.use_provider(None)          # drop the cached provider so the override takes
    llm = LLMApiClient()
    model = llm.embedding_model or args.provider

    repo = CurriculumRepository()
    rows = repo.chunks_for_reembed()
    usable = [r for r in rows if (r.get("embed_text") or "").strip()]
    skipped = len(rows) - len(usable)

    print(f"=== re-embed  provider={args.provider}  model={model}  -> {args.column} ===")
    print(f"    {len(rows)} lesson_plan chunks, {len(usable)} with embed_text"
          + (f", {skipped} SKIPPED (no embed_text — re-ingest those from PDF)" if skipped else ""))
    if args.limit:
        usable = usable[:args.limit]
        print(f"    --limit {args.limit}: embedding {len(usable)}")
    if not usable:
        print("nothing to do.")
        return 0

    if args.dry_run:
        lens = sorted(len(r["embed_text"]) for r in usable)
        print(f"    dry run — would embed {len(usable)} chunks "
              f"(chars: min={lens[0]} median={lens[len(lens)//2]} max={lens[-1]})")
        print(f"    dry run — would write {args.column} + {_model_col(args.column)} on each")
        return 0

    written = 0
    for start in range(0, len(usable), args.batch):
        batch = usable[start:start + args.batch]
        # is_query defaults False: these are stored DOCUMENTS. Getting this backwards is silent —
        # it produces perfectly valid vectors in the wrong half of the model's space.
        vectors = llm.embed_many([r["embed_text"] for r in batch])
        for row, vector in zip(batch, vectors):
            repo.set_embedding(row["id"], vector, model, column=args.column)
            written += 1
        print(f"    {written}/{len(usable)}", end="\r", flush=True)

    print(f"\ndone: {written} chunks now carry {model} vectors in {args.column}.")
    if args.column != INCUMBENT:
        print(f"      retrieve against them by passing use_alt=true "
              f"(scripts.query_curriculum --use-alt).")
    print(f"      NEXT: derive the gate for this model — "
          f"python -m scripts.calibrate_gate --provider {args.provider} --column {args.column}")
    return 0


def _model_col(column: str) -> str:
    return "embedding_model" if column == INCUMBENT else f"{column}_model"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="reembed_curriculum", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--provider", default="gemini", choices=("gemini", "ollama", "openai"),
                   help="embedding provider to use for this run (default: gemini)")
    p.add_argument("--column", default="embedding_alt", choices=("embedding", "embedding_alt"),
                   help="which vector column to write (default: embedding_alt, the challenger)")
    p.add_argument("--batch", type=int, default=64, help="chunks per embed call (default 64)")
    p.add_argument("--limit", type=int, help="only embed the first N chunks (smoke test)")
    p.add_argument("--dry-run", action="store_true", help="report what would happen, embed nothing")
    p.add_argument("--force", action="store_true",
                   help=f"permit overwriting `{INCUMBENT}` (destroys the current baseline)")
    p.set_defaults(func=cmd_reembed)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
