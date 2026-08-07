"""Project Read parser — running header + concept carry-forward (11 books, 187pp).

These books carry NO 'Name of Activity:' body delimiter. Each page header carries the stage;
the concept is carried forward from the last explicit heading until it changes. A new chunk
starts when the (concept, stage, sequence_no) key changes.

Two passes: (1) annotate every page with its normalised stage/seq/concept/title/traits;
(2) segment on the key tuple and build one Unit per run.

Band is document-level, never per-page: the letter comes from the source folder (passed in by the
registry) and the level, if any, from the filename — see bands.py on why page text is not trusted
for it. The same code therefore serves Band A and Band B books.
"""
from __future__ import annotations

from app.entities.curriculum_chunk import Unit
from app.ingestion.bands import band_from_filename
from app.ingestion.constants import CONCEPT_TO_MODULE, RESOURCE_STAGES
from app.ingestion.normalise import (
    normalise_stage,
    normalise_title,
    normalise_traits,
    resolve_concept,
)
from app.ingestion.pdf_reader import Document
from app.ingestion.segment import segment

_NAME_OF_ACTIVITY = "name of activity"


class ProjectReadParser:
    name = "project_read"

    def matches(self, doc: Document) -> bool:
        """Owns any document with ZERO 'Name of Activity:' hits (the band_book delimiter)."""
        return not any(
            _NAME_OF_ACTIVITY in (p.content_md or "").lower() for p in doc.pages
        )

    def parse(self, doc: Document, band: str = "A") -> list[Unit]:
        doc_band = band_from_filename(doc.source_file, band)

        # Pass 1 — annotate pages in reading order (concept carry-forward is stateful).
        prev_concept: str | None = None
        for p in doc.pages:
            stage, seq = normalise_stage(p.raw_header)
            p.stage = stage
            p.sequence_no = seq
            p.activity_title = normalise_title(p.activity_title)
            p.writing_traits = normalise_traits(p.writing_traits)
            # concept switches only on an explicit heading (the bold centred body title)
            concept = resolve_concept(prev_concept, p.activity_title, stage)
            p.concept = concept
            prev_concept = concept

        # Pass 2 — segment on the key tuple and build one Unit per run.
        groups = segment(
            doc.pages, key_of=lambda p: (p.concept, p.stage, p.sequence_no)
        )
        units: list[Unit] = []
        for group in groups:
            head = group[0]
            stage = head.stage or "unknown"
            units.append(
                Unit(
                    pages=group,
                    band=doc_band,
                    module=CONCEPT_TO_MODULE.get(head.concept or ""),
                    concept=head.concept,
                    stage=stage,
                    sequence_no=head.sequence_no,
                    activity_title=head.activity_title,
                    doc_type="resource" if stage in RESOURCE_STAGES else "lesson_plan",
                    source_file=doc.source_file,
                )
            )
        return units
