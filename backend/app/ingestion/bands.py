"""Band ↔ source-folder mapping — the single source of truth for per-band ingestion.

Source PDFs live under data/curriculum/<band folder>/ so a file's band is known from *where it
sits*, not guessed from its contents. This module is deliberately dependency-light (pathlib + re)
so the offline CLI can import it without pulling in embeddings or Supabase.

    data/curriculum/band_a/…   -> band "A"   (validated: band_book + project_read layouts)
    data/curriculum/band_b/…   -> band "B"   (same two layouts as A — reuses both parsers)
    data/curriculum/band_c/…   -> band "C"   (layout not yet analysed — stub parser)

A file placed directly in data/curriculum/ (legacy flat layout) defaults to band "A".

The folder band is the LETTER; the sub-band digit (A1/A2/A3, B1/B2/B3) still comes from the
document — filename token first, then body text. The helpers below are band-scoped so a Band B
book can never be labelled 'A1': they only ever look for the letter the folder already fixed.
"""
from __future__ import annotations
import re
from pathlib import Path

# Ingestion order is the dict order: A, then B, then the not-yet-implemented C.
BAND_DIRS: dict[str, str] = {"A": "band_a", "B": "band_b", "C": "band_c"}
FOLDER_TO_BAND: dict[str, str] = {folder: band for band, folder in BAND_DIRS.items()}

SUB_BANDS = "123"


def band_for_path(path: str | Path) -> str:
    """Band for a PDF, from its parent folder name. Legacy flat path -> 'A'."""
    return FOLDER_TO_BAND.get(Path(path).parent.name, "A")


def default_sub_band(band: str = "A") -> str:
    """Baseline when the document carries no sub-band token: the band's first level."""
    return f"{band}1"


def band_from_filename(source_file: str, band: str = "A") -> str:
    """'2_A1.pdf' -> 'A1'; '5_B2.pdf' -> 'B2'. Defaults to <band>1 when no token is present.

    No \\b before the letter on purpose: the corpus names files '2_A1.pdf', and '_' is a word
    character, so a word boundary would never match there.
    """
    m = re.search(rf"{re.escape(band)}([{SUB_BANDS}])", source_file or "")
    return f"{band}{m.group(1)}" if m else default_sub_band(band)


def band_in_text(text: str | None, band: str = "A") -> str | None:
    """First standalone <band>1/2/3 token in the text, else None (body/header prose)."""
    m = re.search(rf"\b{re.escape(band)}([{SUB_BANDS}])\b", text or "")
    return f"{band}{m.group(1)}" if m else None
