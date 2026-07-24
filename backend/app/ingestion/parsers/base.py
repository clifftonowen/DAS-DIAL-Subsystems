"""Parser protocol — both layout parsers satisfy this shape.

    matches(doc) -> bool     : does this parser own the document's boundary signal?
    parse(doc)   -> [Unit]   : segment the pages into teaching units (no embedding, no DB)

parse takes the whole Document (not just pages) because a Unit needs the source_file and the
band, which are document-level. Both parsers segment doc.pages via the universal segment().
"""
from __future__ import annotations
from typing import Protocol

from app.entities.curriculum_chunk import Unit
from app.ingestion.pdf_reader import Document


class Parser(Protocol):
    name: str

    def matches(self, doc: Document) -> bool: ...

    def parse(self, doc: Document) -> list[Unit]: ...
