"""Band C parser — STUB. Chunk formatting intentionally empty until Band C PDFs exist.

Mirror of band_b.py: reached only via the folder→band switch (data/curriculum/band_c/), emits no
chunks yet because the Band C layout has not been analysed. See band_b.py for the "when real PDFs
arrive" checklist.
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

    def parse(self, doc: Document) -> list[Unit]:
        log.warning(
            "Band C parsing not implemented — %s produced 0 chunks. Dry-run the PDF, then reuse "
            "band_book/project_read or implement segmentation in band_c.py.", doc.source_file
        )
        return []
