"""Band ↔ source-folder mapping — the single source of truth for per-band ingestion.

Source PDFs live under data/curriculum/<band folder>/ so a file's band is known from *where it
sits*, not guessed from its contents. This module is deliberately dependency-light (pathlib + re)
so the offline CLI can import it without pulling in embeddings or Supabase.

    data/curriculum/band_a/…   -> band "A"   (validated: band_book + project_read layouts)
    data/curriculum/band_b/…   -> band "B"   (same two layouts as A — reuses both parsers)
    data/curriculum/band_c/…   -> band "C"   (layout not yet analysed — stub parser)

A file placed directly in data/curriculum/ (legacy flat layout) defaults to band "A".

LEVEL (the digit) is a separate question from BAND (the letter), and only ONE kind of evidence is
trusted for it: a band book naming its own level in its FILENAME. Page text is deliberately not
consulted — '2) A1.pdf' mentions 'A3' on as many pages as it mentions 'A1', so a body token says
nothing reliable about the book it sits in. Every other PDF therefore carries the bare letter,
which is also what learners.band_group holds ('A' | 'B' | 'C'), so the two line up directly.
"""
from __future__ import annotations
import re
from pathlib import Path

# Ingestion order is the dict order: A, then B, then the not-yet-implemented C.
BAND_DIRS: dict[str, str] = {"A": "band_a", "B": "band_b", "C": "band_c"}
FOLDER_TO_BAND: dict[str, str] = {folder: band for band, folder in BAND_DIRS.items()}

# Level tokens a band book may name itself with, per band. Only the three Band A books do
# ('2) A1.pdf', '3) A2.pdf', '4) A3.pdf'); B and C have no entry, so their chunks keep the bare
# letter. Add a tuple here if levelled B/C books ever arrive — but note the learner scale runs
# B4-B6 and C7-C9, NOT B1-B3: a level invented here would match no learner.
BAND_LEVELS: dict[str, tuple[str, ...]] = {"A": ("A1", "A2", "A3")}


def band_for_path(path: str | Path) -> str:
    """Band for a PDF, from its parent folder name. Legacy flat path -> 'A'."""
    return FOLDER_TO_BAND.get(Path(path).parent.name, "A")


def band_from_filename(source_file: str, band: str = "A") -> str:
    """'2) A1.pdf' -> 'A1'. Any filename without a level token -> the bare band letter.

    No word boundary before the token on purpose: the corpus also names files '2_A1.pdf', and
    '_' is a word character, so \\b would never match there.
    """
    for level in BAND_LEVELS.get(band, ()):
        if re.search(rf"{re.escape(level)}\b", source_file or "", re.IGNORECASE):
            return level
    return band
