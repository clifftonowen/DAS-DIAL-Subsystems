"""Project Read parser — running header + concept carry-forward (11 books, 187pp).

These books carry NO 'Name of Activity:' body delimiter. Each page header carries the stage;
the concept is carried forward from the last explicit heading until it changes. A new chunk
starts when the (concept, stage, sequence_no) key changes.

Two passes: (1) annotate every page with its normalised stage/seq/concept/title/traits and a
carried-forward band; (2) segment on the key tuple and build one Unit per run.
"""
from __future__ import annotations
import re

from app.entities.curriculum_chunk import Unit
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
_BAND_RE = re.compile(r"\bA([123])\b")     # 'A1' | 'A2' | 'A3' token
DEFAULT_BAND = "A1"                         # Barebone Sentence baseline (spec example)


def _detect_band(*texts: str | None) -> str | None:
    """First A1/A2/A3 token across the given texts, else None."""
    for text in texts:
        m = _BAND_RE.search(text or "")
        if m:
            return "A" + m.group(1)
    return None


class ProjectReadParser:
    name = "project_read"

    def matches(self, doc: Document) -> bool:
        """Owns any document with ZERO 'Name of Activity:' hits (the band_book delimiter)."""
        return not any(
            _NAME_OF_ACTIVITY in (p.content_md or "").lower() for p in doc.pages
        )

    def parse(self, doc: Document) -> list[Unit]:
        # Pass 1 — annotate pages in reading order (carry-forward is stateful).
        band_by_page: dict[int, str] = {}
        prev_concept: str | None = None
        prev_band = DEFAULT_BAND
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
            band = _detect_band(p.raw_header, p.content_md) or prev_band
            prev_band = band
            band_by_page[p.number] = band

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
                    band=band_by_page[head.number],
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
