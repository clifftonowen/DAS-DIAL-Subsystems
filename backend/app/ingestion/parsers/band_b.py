"""Band B parser — STUB. Chunk formatting intentionally empty until Band B PDFs exist.

The pipeline switches to this parser purely by folder (data/curriculum/band_b/), never by content
detection, so `matches()` returns False. `parse()` produces NO chunks yet: the Band B layout has
not been analysed, and the corpus rule is that chunking is deterministic and format-specific — a
guessed segmenter would emit wrong boundaries, which is worse than none.

When real Band B PDFs are available: dry-run one to inspect its layout, then either
  - reuse an existing parser (if it carries the 'Name of Activity:' delimiter -> band_book, or a
    running-header layout -> project_read), by registering it for band "B" in registry.py; or
  - implement segmentation here, calling the shared segment() with a band-appropriate key_of.
"""
from __future__ import annotations
import logging

from app.entities.curriculum_chunk import Unit
from app.ingestion.pdf_reader import Document

log = logging.getLogger(__name__)


class BandBParser:
    name = "band_b"

    def matches(self, doc: Document) -> bool:
        """Never auto-detected; the pipeline reaches this parser via the folder→band switch."""
        return False

    def parse(self, doc: Document) -> list[Unit]:
        log.warning(
            "Band B parsing not implemented — %s produced 0 chunks. Dry-run the PDF, then reuse "
            "band_book/project_read or implement segmentation in band_b.py.", doc.source_file
        )
        return []
