"""Band C parser — STUB. Chunk formatting intentionally empty until Band C PDFs exist.

Reached only via the folder→band switch (data/curriculum/band_c/), never by content detection, so
`matches()` returns False. `parse()` produces NO chunks yet: the Band C layout has not been
analysed, and the corpus rule is that chunking is deterministic and format-specific — a guessed
segmenter would emit wrong boundaries, which is worse than none.

When real Band C PDFs arrive: dry-run one to inspect its layout. If it turns out to share the
Band A/B layouts (a 'Name of Activity:' delimiter -> band_book, or a running-header layout ->
project_read), the fix is to DELETE this stub and drop "C" from registry.BAND_STUBS — that is
exactly what Band B did. Otherwise implement segmentation here, calling the shared segment() with
a band-appropriate key_of.
"""
from __future__ import annotations
import logging

from app.entities.curriculum_chunk import Unit
from app.ingestion.pdf_reader import Document

log = logging.getLogger(__name__)


class BandCParser:
    name = "band_c"

    def matches(self, doc: Document) -> bool:
        """Never auto-detected; the pipeline reaches this parser via the folder→band switch."""
        return False

    def parse(self, doc: Document, band: str = "C") -> list[Unit]:
        log.warning(
            "Band C parsing not implemented — %s produced 0 chunks. Dry-run the PDF, then reuse "
            "band_book/project_read or implement segmentation in band_c.py.", doc.source_file
        )
        return []
