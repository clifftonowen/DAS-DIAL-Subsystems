"""Curriculum ingestion domain models (Entity layer, Subsystem 3).

Plain pydantic models — no persistence logic here.

Three stages of the offline pipeline:
    Page   -> one physical PDF page after positional + normalise extraction
    Unit   -> a run of pages sharing one (module, concept, stage, sequence_no) key
    CurriculumChunk -> one aggregated, embeddable teaching unit == one DB row

`CurriculumChunk` mirrors the `curriculum_chunks` table in infra/schema.sql column-for-column
(the repository maps it to/from a dict). `embedding` and the bookkeeping columns ride along on
the entity so the pipeline can populate them before upsert.
"""
from __future__ import annotations
from pydantic import BaseModel, Field
from uuid import UUID, uuid4


class Page(BaseModel):
    """One physical PDF page after positional extraction + normalisation.

    Positional fields come from pdf_reader (by y-coordinate, never grep).
    The lower `# carried by normalise / parser` block is derived state used as the
    segmentation key — carry-forward writes `concept`/`stage`, band_book writes
    `current_activity_name`.
    """
    number: int                              # 0-based page index within the source PDF
    printed_no: str | None = None            # footer printed page number (y/H > 0.90)
    raw_header: str | None = None            # header band text (0.06 < y/H < 0.14)
    activity_title: str | None = None        # first bold centred body line
    content_md: str = ""                     # full page text
    answer_key: str | None = None            # routed here when page is an answer key
    is_answer_key: bool = False              # matches 'answer key' | 'suggested answers'
    writing_traits: list[str] = []           # 6+1 box, lowercased; empty if absent
    has_images: bool = False                 # image-only-page detection input

    # carried by normalise / parser (segmentation key state)
    concept: str | None = None               # explicit heading, else carried forward
    stage: str | None = None                 # canonical enum, never None after normalise
    sequence_no: int = 1                     # Practice worksheet 1 vs 2 vs 3
    current_activity_name: str | None = None # band_book 'Name of Activity:' delimiter


class Unit(BaseModel):
    """A run of pages a parser grouped under one segmentation key.

    Parsers fill the metadata they know (carry-forward concept, header stage, band from the
    book); chunk_builder aggregates the pages into a CurriculumChunk.
    """
    pages: list[Page] = []
    band: str | None = None
    module: str | None = None
    concept: str | None = None
    stage: str | None = None
    sequence_no: int = 1
    activity_title: str | None = None
    doc_type: str = "lesson_plan"            # 'lesson_plan' | 'resource'
    source_file: str = ""


class CurriculumChunk(BaseModel):
    """One aggregated teaching unit == one `curriculum_chunks` row.

    Metadata is primary (used in WHERE); the vector is a safety net (used in ORDER BY).
    """
    id: UUID = Field(default_factory=uuid4)

    # filters (indexed, used in WHERE)
    band: str                                # 'A1' | 'A2' | 'A3' (finer than learners.band_level)
    module: str | None = None                # 'Barebone Sentence' | 'Predicate Expanders'
    concept: str                             # 'action_predicate' | 'all' | ... curriculum join key
    stage: str | None = None                 # 'presentation' | 'practice' | ...
    sequence_no: int = 1                     # Practice worksheet 1 vs 2 vs 3 — required
    doc_type: str = "lesson_plan"            # 'lesson_plan' | 'resource'
    writing_traits: list[str] = []           # 6+1, lowercased; optional filter (63% coverage)
    cognitive_constructs: list[str] = []     # construct tags; see ingestion/constants.py

    # content (fed to the LLM after retrieval)
    activity_title: str | None = None        # body heading; best discriminator on metadata ties
    content_md: str                          # full worksheet / teaching text — never trimmed
    answer_key: str | None = None            # a field of its worksheet, never a separate chunk
    objective: str | None = None             # may be null — extraction unverified

    # guardrail
    prerequisites: list[str] = []            # scope-and-sequence as data

    # provenance
    source_file: str
    page_start: str | None = None
    page_end: str | None = None

    # vector + bookkeeping
    embedding: list[float] | None = None     # 768-dim (nomic-embed-text); populated by the pipeline before upsert
    embedding_model: str | None = None
    ingest_version: str | None = None
    raw_header: str | None = None            # debugging
    embed_text: str | None = None            # optional: "why did this match?"

    # reserved for v2 — create, leave empty
    skills: list[str] = []
