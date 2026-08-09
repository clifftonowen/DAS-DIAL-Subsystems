"""Aggregate a Unit (run of pages) into one CurriculumChunk.

Answer-key pages become the chunk's `answer_key` FIELD, never separate content. The rest of the
pages aggregate into `content_md` — full text, never trimmed or summarised. `embed_text` is the
metadata prefix + the full content (the only string that discriminates chunks sharing metadata).

Guardrail/bridge columns come from the static taxonomy: cognitive_constructs and prerequisites
are looked up by concept. `skills` stays empty (reserved for v2). A chunk is dropped only if its
aggregated content is still < THIN_CHUNK_MIN chars — a safety net, not a routine filter.
"""
from __future__ import annotations

from app.entities.curriculum_chunk import CurriculumChunk, Unit
from app.ingestion.constants import CONCEPT_TO_CONSTRUCTS, PREREQUISITES
from app.ingestion.normalise import fold_unicode

THIN_CHUNK_MIN = 100          # < this many cleaned chars after aggregation -> drop
EMBED_CHAR_LIMIT = 30000      # ~8191-token model limit; truncate rather than error


def _clean(text: str | None) -> str:
    """Fold unicode and trim, preserving internal line structure of worksheets."""
    return fold_unicode(text or "").strip()


def _page_label(page) -> str:
    """Printed page number when present, else the 0-based index as a string."""
    return page.printed_no or str(page.number)


def build_embed_text(c: CurriculumChunk) -> str:
    """Metadata prefix + FULL content_md. The `|` prefix is plain text (not parsed by the
    embedder); columns are assigned separately in Python. Truncated at the model limit."""
    prefix = (
        f"Band {c.band} | {c.module or ''} | {c.concept} | "
        f"{c.stage or ''} | {c.activity_title or ''}"
    )
    return f"{prefix}\n{c.content_md}"[:EMBED_CHAR_LIMIT]


def build_chunk(unit: Unit, ingest_version: str | None = None) -> CurriculumChunk | None:
    """One Unit -> one CurriculumChunk (embedding filled later by the pipeline). None if thin."""
    content_parts = [_clean(p.content_md) for p in unit.pages if not p.is_answer_key]
    answer_parts = [_clean(p.answer_key or p.content_md) for p in unit.pages if p.is_answer_key]

    content_md = "\n\n".join(part for part in content_parts if part).strip()
    if len(content_md) < THIN_CHUNK_MIN:
        return None  # safety net — measured: no corpus chunk hits this

    answer_key = "\n\n".join(part for part in answer_parts if part).strip() or None
    writing_traits = sorted({t for p in unit.pages for t in (p.writing_traits or [])})

    concept = unit.concept or "all"
    chunk = CurriculumChunk(
        band=unit.band or "A1",
        module=unit.module,
        concept=concept,
        stage=unit.stage,
        sequence_no=unit.sequence_no,
        doc_type=unit.doc_type,
        writing_traits=writing_traits,
        cognitive_constructs=list(CONCEPT_TO_CONSTRUCTS.get(concept, [])),
        activity_title=unit.activity_title,
        content_md=content_md,
        answer_key=answer_key,
        objective=None,                       # extraction unverified — may stay null
        prerequisites=list(PREREQUISITES.get(concept, [])),
        source_file=unit.source_file,
        page_start=_page_label(unit.pages[0]) if unit.pages else None,
        page_end=_page_label(unit.pages[-1]) if unit.pages else None,
        ingest_version=ingest_version,
        raw_header=unit.pages[0].raw_header if unit.pages else None,
        skills=[],                            # reserved for v2 — leave empty
    )
    chunk.embed_text = build_embed_text(chunk)
    return chunk


def build_chunks(units: list[Unit], ingest_version: str | None = None) -> list[CurriculumChunk]:
    """Build all non-thin chunks for a document."""
    built = (build_chunk(u, ingest_version) for u in units)
    return [c for c in built if c is not None]
