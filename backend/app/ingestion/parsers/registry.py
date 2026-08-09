"""Parser detection — step zero of chunking.

Two-level selection. FIRST by band (known from the source folder, see bands.py): Band C routes to
its stub parser, whose layout has not been analysed yet. Bands A and B share the same two layouts,
so both select by CONTENT — the matchers are mutually exclusive and total: band_book owns any
document with a 'Name of Activity:' delimiter; project_read owns everything else (the delimiter's
absence). Using the wrong boundary signal yields zero chunks or one giant chunk, so detect FIRST.

The band letter is still carried separately into parse(band=...) — content picks the LAYOUT, the
folder fixes the BAND, and the two must not be conflated.
"""
from __future__ import annotations

from app.ingestion.pdf_reader import Document
from app.ingestion.parsers.base import Parser
from app.ingestion.parsers.band_book import BandBookParser
from app.ingestion.parsers.band_c import BandCParser
from app.ingestion.parsers.project_read import ProjectReadParser

# Order matters: band_book's positive delimiter signal is checked first; project_read is the
# catch-all fallback (it matches on the ABSENCE of the delimiter).
PARSERS: tuple[Parser, ...] = (BandBookParser(), ProjectReadParser())

# Bands whose layout is not yet analysed: routed by folder to an empty stub, never by content.
BAND_STUBS: dict[str, Parser] = {"C": BandCParser()}


def detect_parser(doc: Document, band: str = "A") -> Parser:
    """Return the parser for this document: by band first (C stub), else by content signal."""
    stub = BAND_STUBS.get(band)
    if stub is not None:
        return stub
    for parser in PARSERS:
        if parser.matches(doc):
            return parser
    # Unreachable: project_read matches every document without the band delimiter.
    raise ValueError(f"No parser matched {doc.source_file!r}")
