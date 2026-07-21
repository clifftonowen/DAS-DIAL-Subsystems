"""Parser detection — step zero of chunking.

Using the wrong boundary signal yields zero chunks or one giant chunk, so detect FIRST. The two
parsers' matchers are mutually exclusive and total: band_book owns any document with a
'Name of Activity:' delimiter; project_read owns everything else (the delimiter's absence).
"""
from __future__ import annotations

from app.ingestion.pdf_reader import Document
from app.ingestion.parsers.base import Parser
from app.ingestion.parsers.band_book import BandBookParser
from app.ingestion.parsers.project_read import ProjectReadParser

# Order matters: band_book's positive delimiter signal is checked first; project_read is the
# catch-all fallback (it matches on the ABSENCE of the delimiter).
PARSERS: tuple[Parser, ...] = (BandBookParser(), ProjectReadParser())


def detect_parser(doc: Document) -> Parser:
    """Return the single parser that owns this document's boundary signal."""
    for parser in PARSERS:
        if parser.matches(doc):
            return parser
    # Unreachable: project_read matches every document without the band delimiter.
    raise ValueError(f"No parser matched {doc.source_file!r}")
