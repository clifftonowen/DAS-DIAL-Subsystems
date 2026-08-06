"""Ingestion orchestration: read -> detect -> parse -> build -> embed -> store.

The one place the offline steps compose. Idempotent: delete_by_source() wipes a source's chunks
before insert, so re-running rebuilds cleanly with no duplicates. Supabase access goes only
through CurriculumRepository; embeddings only through LLMApiClient. Image-only pages are skipped
for chunking (they never form a Unit with content) but LOGGED to data/curriculum/_orphans.log —
never silently dropped.
"""
from __future__ import annotations
from functools import lru_cache
from pathlib import Path

from app.core.config import settings
from app.gateways.llm_client import LLMApiClient
from app.ingestion.bands import BAND_DIRS, band_for_path
from app.ingestion.chunk_builder import build_chunks
from app.ingestion.parsers.registry import detect_parser
from app.ingestion.pdf_reader import Document, read_pdf
from app.repositories.curriculum_repository import CurriculumRepository

INGEST_VERSION = "v1"
DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "curriculum"
ORPHAN_LOG = DATA_DIR / "_orphans.log"
IMAGE_ONLY_MAX_CHARS = 30  # image + < this much real text => image-only page


@lru_cache
def _repo() -> CurriculumRepository:
    return CurriculumRepository()


@lru_cache
def _llm() -> LLMApiClient:
    return LLMApiClient()


def _to_row(chunk) -> dict:
    """Serialise a CurriculumChunk to a JSON-safe row for Supabase (UUID -> str)."""
    data = chunk.model_dump() if hasattr(chunk, "model_dump") else chunk.dict()
    data["id"] = str(data["id"])
    return data


def _log_orphans(doc: Document) -> int:
    """Append image-only pages to _orphans.log. Returns how many were logged."""
    orphans = [
        p for p in doc.pages
        if p.has_images and len((p.content_md or "").strip()) < IMAGE_ONLY_MAX_CHARS
    ]
    if not orphans:
        return 0
    ORPHAN_LOG.parent.mkdir(parents=True, exist_ok=True)
    with ORPHAN_LOG.open("a") as fh:
        for p in orphans:
            chars = len((p.content_md or "").strip())
            fh.write(f"{doc.source_file}\tpage {p.number} (printed {p.printed_no})\t"
                     f"image-only, {chars} chars\n")
    return len(orphans)


def ingest_file(path: str | Path, no_embed: bool = False, band: str | None = None) -> int:
    """Ingest one PDF end-to-end. Returns the number of chunks stored.

    band defaults to the source folder's band (data/curriculum/<band folder>/); A and B share the
    two layout parsers, C routes to an empty stub until its layout is analysed.
    """
    band = band or band_for_path(path)
    doc = read_pdf(path)
    parser = detect_parser(doc, band=band)
    units = parser.parse(doc, band=band)
    chunks = build_chunks(units, ingest_version=INGEST_VERSION)
    _log_orphans(doc)

    if not no_embed:
        vectors = _llm().embed_many([c.embed_text or "" for c in chunks])
        for chunk, vector in zip(chunks, vectors):
            chunk.embedding = vector
            chunk.embedding_model = settings.embedding_model

    rows = [_to_row(c) for c in chunks]
    repo = _repo()
    repo.delete_by_source(doc.source_file)  # idempotent: wipe this source, then insert
    if rows:
        repo.upsert_chunks(rows)
    return len(rows)


def ingest_all(no_embed: bool = False) -> int:
    """Ingest every PDF under data/curriculum/<band folder>/. Returns total chunks stored.

    Walks each band folder in turn so a file's band is fixed by where it sits. The Band C folder
    contributes 0 chunks until its stub parser is implemented.
    """
    total = 0
    for band, subdir in BAND_DIRS.items():
        for pdf in sorted((DATA_DIR / subdir).glob("*.pdf")):
            total += ingest_file(pdf, no_embed=no_embed, band=band)
    return total
