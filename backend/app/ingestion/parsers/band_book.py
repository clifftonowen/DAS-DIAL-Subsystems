"""Band-book parser — 'Name of Activity:' body delimiter (A1/A2/A3 band books).

These books (2_A1, 3_A2, 4_A3) start each activity with a 'Name of Activity:' line in the body.
A new chunk begins at every such line; pages after it belong to the same activity until the
next delimiter (carry-forward of the activity name). The band is read from the filename.

Front matter before the first delimiter (cover/TOC, no activity name) is not emitted as a chunk.
"""
from __future__ import annotations
import re

from app.entities.curriculum_chunk import Unit
from app.ingestion.constants import CONCEPT_ALL, CONCEPT_TO_MODULE, RESOURCE_STAGES
from app.ingestion.normalise import (
    clean_text,
    detect_concept,
    normalise_stage,
    normalise_title,
    normalise_traits,
)
from app.ingestion.pdf_reader import Document
from app.ingestion.segment import segment

_NAME_OF_ACTIVITY = "name of activity"
_NAME_RE = re.compile(r"name of activity:\s*(.+)", re.IGNORECASE)
_BAND_RE = re.compile(r"A([123])")
DEFAULT_BAND = "A1"


def _activity_name(content: str | None) -> str | None:
    """The value after 'Name of Activity:' on the page (first line), else None."""
    m = _NAME_RE.search(content or "")
    if not m:
        return None
    return clean_text(m.group(1).splitlines()[0]) or None


def _band_from_filename(source_file: str) -> str:
    """'2_A1.pdf' -> 'A1'; default to A1 if no band token is present."""
    m = _BAND_RE.search(source_file or "")
    return ("A" + m.group(1)) if m else DEFAULT_BAND


class BandBookParser:
    name = "band_book"

    def matches(self, doc: Document) -> bool:
        """Owns any document carrying at least one 'Name of Activity:' delimiter."""
        return any(
            _NAME_OF_ACTIVITY in (p.content_md or "").lower() for p in doc.pages
        )

    def parse(self, doc: Document) -> list[Unit]:
        band = _band_from_filename(doc.source_file)

        # Pass 1 — carry the activity name forward across its pages.
        prev_name: str | None = None
        for p in doc.pages:
            name = _activity_name(p.content_md)
            if name:
                prev_name = name
            p.current_activity_name = prev_name
            stage, seq = normalise_stage(p.raw_header)
            p.stage = stage
            p.sequence_no = seq
            p.writing_traits = normalise_traits(p.writing_traits)

        # Pass 2 — segment on the delimiter; drop leading front matter (name is None).
        groups = segment(doc.pages, key_of=lambda p: p.current_activity_name)
        units: list[Unit] = []
        for group in groups:
            head = group[0]
            name = head.current_activity_name
            if name is None:
                continue  # front matter before the first delimiter
            concept = detect_concept(name) or CONCEPT_ALL
            stage = head.stage or "unknown"
            units.append(
                Unit(
                    pages=group,
                    band=band,
                    module=CONCEPT_TO_MODULE.get(concept),
                    concept=concept,
                    stage=stage,
                    sequence_no=head.sequence_no,
                    activity_title=normalise_title(name),
                    doc_type="resource" if stage in RESOURCE_STAGES else "lesson_plan",
                    source_file=doc.source_file,
                )
            )
        return units
