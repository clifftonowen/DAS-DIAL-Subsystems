"""Band ↔ source-folder mapping — the single source of truth for per-band ingestion.

Source PDFs live under data/curriculum/<band folder>/ so a file's band is known from *where it
sits*, not guessed from its contents. This module is deliberately dependency-light (only pathlib)
so the offline CLI can import it without pulling in embeddings or Supabase.

    data/curriculum/band_a/…   -> band "A"   (validated: band_book + project_read layouts)
    data/curriculum/band_b/…   -> band "B"   (layout not yet analysed — stub parser)
    data/curriculum/band_c/…   -> band "C"   (layout not yet analysed — stub parser)

A file placed directly in data/curriculum/ (legacy flat layout) defaults to band "A".
"""
from __future__ import annotations
from pathlib import Path

# Ingestion order is the dict order: A first, then the not-yet-implemented B and C.
BAND_DIRS: dict[str, str] = {"A": "band_a", "B": "band_b", "C": "band_c"}
FOLDER_TO_BAND: dict[str, str] = {folder: band for band, folder in BAND_DIRS.items()}


def band_for_path(path: str | Path) -> str:
    """Band for a PDF, from its parent folder name. Legacy flat path -> 'A'."""
    return FOLDER_TO_BAND.get(Path(path).parent.name, "A")
