"""CLI entry point for offline curriculum ingestion (run from backend/).

    python -m scripts.ingest_curriculum run    --file data/curriculum/band_a/2_A1.pdf [--dry-run] [--no-embed]
    python -m scripts.ingest_curriculum run    --band b [--dry-run] [--no-embed]
    python -m scripts.ingest_curriculum run    --all [--dry-run] [--no-embed]
    python -m scripts.ingest_curriculum verify --source 2_A1.pdf

--band <a|b|c> ingests exactly one band folder (data/curriculum/band_<x>/), so re-running a band
costs nothing on the others; --all walks every band folder in BAND_DIRS order.

--dry-run prints the chunk table (band | module | concept | stage | seq | pages | key | chars |
title) WITHOUT calling the embedding gateway or the database. Always dry-run a new book first.

The parse->build path (read -> detect -> parse -> build) needs no secrets and runs offline; only
the non-dry `run` reaches the pipeline (embeddings + Supabase), imported lazily so this CLI loads
without those deps for a dry-run.
"""
from __future__ import annotations
import argparse
from pathlib import Path

from app.entities.curriculum_chunk import CurriculumChunk

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "curriculum"
INGEST_VERSION = "v1"


def parse_pdf(path: Path) -> tuple[str, list[CurriculumChunk]]:
    """Read + detect + parse + build (no embedding, no DB). Returns (parser_name, chunks)."""
    from app.ingestion.bands import band_for_path
    from app.ingestion.pdf_reader import read_pdf
    from app.ingestion.parsers.registry import detect_parser
    from app.ingestion.chunk_builder import build_chunks

    band = band_for_path(path)
    doc = read_pdf(path)
    parser = detect_parser(doc, band=band)
    units = parser.parse(doc, band=band)
    return parser.name, build_chunks(units, ingest_version=INGEST_VERSION)


def _resolve_paths(file: str | None, all_: bool, band: str | None = None) -> list[Path]:
    """The PDFs one `run` invocation covers: one file, one band folder, or the whole corpus."""
    from app.ingestion.bands import BAND_DIRS

    if all_:
        return sorted(DATA_DIR.glob("**/*.pdf"))  # recurse into band_a/ band_b/ band_c/
    if band:
        subdir = BAND_DIRS.get(band.upper())
        if subdir is None:
            raise SystemExit(f"Unknown band {band!r} — expected one of {list(BAND_DIRS)}.")
        return sorted((DATA_DIR / subdir).glob("*.pdf"))
    if file:
        return [Path(file)]
    return []


def format_chunk_table(chunks: list[CurriculumChunk]) -> str:
    """Human-scannable dry-run table — one row per chunk, plus a summary line."""
    header = (f"{'band':<5} {'module':<18} {'concept':<18} {'stage':<14} {'seq':>3} "
              f"{'pages':>9} {'key':>3} {'chars':>6}  title")
    rows = [header, "-" * len(header)]
    for c in chunks:
        pages = f"{c.page_start or '?'}-{c.page_end or '?'}"
        rows.append(
            f"{c.band:<5.5} {(c.module or '-'):<18.18} {c.concept:<18.18} "
            f"{(c.stage or '-'):<14.14} {c.sequence_no:>3} {pages:>9} "
            f"{'Y' if c.answer_key else '-':>3} {len(c.content_md):>6}  {c.activity_title or '-'}"
        )
    traits_cov = sum(1 for c in chunks if c.writing_traits)
    pct = (100 * traits_cov // len(chunks)) if chunks else 0
    rows.append(f"\n{len(chunks)} chunks | traits on {traits_cov} ({pct}%) | "
                f"resources: {sum(1 for c in chunks if c.doc_type == 'resource')}")
    return "\n".join(rows)


def cmd_run(args: argparse.Namespace) -> int:
    paths = _resolve_paths(args.file, args.all, args.band)
    if not paths:
        print("Nothing to do: pass --file <pdf>, --band <a|b|c>, or --all "
              f"(searched {DATA_DIR}).")
        return 1

    total = 0
    for path in paths:
        if not path.exists():
            print(f"!! missing: {path}")
            continue
        parser_name, chunks = parse_pdf(path)
        total += len(chunks)
        print(f"\n=== {path.name}  [{parser_name}]  {len(chunks)} chunks ===")
        if args.dry_run:
            print(format_chunk_table(chunks))
        else:
            from app.ingestion.pipeline import ingest_file  # lazy: needs embeddings + Supabase
            n = ingest_file(path, no_embed=args.no_embed)
            print(f"stored {n} chunks")
    print(f"\nTOTAL: {total} chunks across {len(paths)} file(s)"
          + ("  (dry-run — nothing embedded or stored)" if args.dry_run else ""))
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    """Offline sanity check for one source: rebuild chunks and assert the ingestion invariants."""
    if Path(args.source).exists():
        path = Path(args.source)
    else:  # bare filename — search the band subfolders
        path = next(DATA_DIR.glob(f"**/{args.source}"), None)
    if path is None or not path.exists():
        print(f"!! missing: {args.source} (searched {DATA_DIR}/**/)")
        return 1

    parser_name, chunks = parse_pdf(path)
    print(f"=== verify {path.name}  [{parser_name}]  {len(chunks)} chunks ===")

    checks = {
        "chunks built": len(chunks) > 0,
        "no stage=None": all(c.stage is not None for c in chunks),
        "no empty content (< 100 chars)": all(len(c.content_md) >= 100 for c in chunks),
        "skills empty on every row": all(c.skills == [] for c in chunks),
        "embed_text = prefix + content": all(
            c.embed_text and c.content_md in c.embed_text for c in chunks
        ),
    }
    for label, passed in checks.items():
        print(f"  [{'ok' if passed else 'FAIL'}] {label}")

    # sequence_no distinctness within (concept, stage) — worksheet 1/2/3 must differ
    seen: dict[tuple, set] = {}
    for c in chunks:
        seen.setdefault((c.concept, c.stage), set()).add(c.sequence_no)
    multi = {k: sorted(v) for k, v in seen.items() if len(v) > 1}
    if multi:
        print(f"  distinct sequence_no groups: {multi}")

    return 0 if all(checks.values()) else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ingest_curriculum", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="parse (and, without --dry-run, embed + store) books")
    src = run.add_mutually_exclusive_group(required=True)
    src.add_argument("--file", help="a single PDF path")
    src.add_argument("--band", help="every PDF in one band folder, e.g. --band b")
    src.add_argument("--all", action="store_true", help="every PDF in data/curriculum/")
    run.add_argument("--dry-run", action="store_true", help="print the chunk table; no embed/DB")
    run.add_argument("--no-embed", action="store_true", help="store rows but skip embeddings")
    run.set_defaults(func=cmd_run)

    ver = sub.add_parser("verify", help="rebuild one source and assert ingestion invariants")
    ver.add_argument("--source", required=True, help="PDF filename in data/curriculum/ or a path")
    ver.set_defaults(func=cmd_verify)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
