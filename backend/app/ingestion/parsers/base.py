"""Parser protocol — both layout parsers satisfy this shape.

    matches(doc)       -> bool     : does this parser own the document's boundary signal?
    parse(doc, band)   -> [Unit]   : segment the pages into teaching units (no embedding, no DB)

parse takes the whole Document (not just pages) because a Unit needs the source_file, which is
document-level. It also takes the band LETTER, which the document itself cannot be trusted for —
it comes from the source folder (bands.py). Parsers resolve only the sub-band digit (A1/A2/A3,
B1/B2/B3) from the filename or page text. Both parsers segment doc.pages via segment().
"""
from __future__ import annotations
from typing import Protocol

from app.entities.curriculum_chunk import Unit
from app.ingestion.pdf_reader import Document


class Parser(Protocol):
    name: str

    def matches(self, doc: Document) -> bool: ...

    def parse(self, doc: Document, band: str = "A") -> list[Unit]: ...
