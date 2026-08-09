"""Positional PDF extraction — PyMuPDF (fitz) is the "eyes", this module is the "brain".

Reads a curriculum PDF into a list[Page] using COORDINATES, never by grepping page text
(non-negotiable rule 5). Headers/footers are read by their y-band; the body title is the first
bold, centred line. fitz is imported lazily (like core.supabase_client imports supabase) so the
rest of the pipeline imports cleanly before PyMuPDF is installed.

Downstream: normalise.py turns raw_header -> stage/sequence_no; the parsers segment; the
pipeline decides image-only skips. This module only reports what is physically on the page.
"""
from __future__ import annotations
import re
from pathlib import Path

from pydantic import BaseModel

from app.entities.curriculum_chunk import Page
from app.ingestion.constants import MODULES, TRAITS, TRAITS_BOX_LABEL

# ── Positional bands (fraction of page height H) ─────────────────────────────
HEADER_TOP = 0.06        # skip the very top margin
HEADER_BOTTOM = 0.14     # header/stage band ends here
FOOTER_TOP = 0.90        # printed page number lives below this
TRAITS_BOX_SPAN = 0.30   # trait words sit within this fraction of H below the 6+1 label
CENTRE_TOL = 0.15        # |span centre - page centre| < CENTRE_TOL*W  => "centred"

FITZ_BOLD_FLAG = 1 << 4  # fitz span flags: bit 4 == bold

ANSWER_KEY_RE = re.compile(r"answer key|suggested answers", re.IGNORECASE)
_DIGITS_RE = re.compile(r"\d+")
_MODULES_LOWER = {m.lower() for m in MODULES}


class Document(BaseModel):
    """A read PDF: its filename and extracted pages. Consumed by detect_parser / parsers."""
    source_file: str
    pages: list[Page] = []


def read_pdf(path: str | Path) -> Document:
    """Open a curriculum PDF and return a Document of positionally-extracted Pages."""
    import fitz  # lazy — PyMuPDF may not be installed until the ingestion env is set up

    path = Path(path)
    pages: list[Page] = []
    with fitz.open(path) as pdf:
        for index, page in enumerate(pdf):
            pages.append(_extract_page(page, index))
    return Document(source_file=path.name, pages=pages)


def _extract_page(page, index: int) -> Page:
    """Extract one fitz page into a Page by span geometry."""
    rect = page.rect
    height = rect.height or 1.0
    width = rect.width or 1.0
    centre_x = width / 2.0

    spans: list[dict] = []  # {"text", "y", "cx", "bold"}
    for block in page.get_text("dict").get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span.get("text", "").strip()
                if not text:
                    continue
                x0, y0, x1, y1 = span.get("bbox", (0, 0, 0, 0))
                spans.append({
                    "text": text,
                    "y": y0 / height,
                    "cx": (x0 + x1) / 2.0,
                    "bold": bool(span.get("flags", 0) & FITZ_BOLD_FLAG),
                })

    header_spans = [s for s in spans if HEADER_TOP < s["y"] < HEADER_BOTTOM]
    footer_spans = [s for s in spans if s["y"] > FOOTER_TOP]
    body_spans = [s for s in spans if HEADER_BOTTOM <= s["y"] <= FOOTER_TOP]

    content_md = page.get_text("text").strip()

    return Page(
        number=index,
        printed_no=_printed_no(footer_spans),
        raw_header=_raw_header(header_spans),
        activity_title=_activity_title(body_spans, centre_x, width),
        content_md=content_md,
        is_answer_key=bool(ANSWER_KEY_RE.search(content_md)),
        writing_traits=_writing_traits(spans, content_md),
        has_images=bool(page.get_images(full=True)),
    )


def _printed_no(footer_spans: list[dict]) -> str | None:
    """First run of digits in the footer band."""
    for s in footer_spans:
        m = _DIGITS_RE.search(s["text"])
        if m:
            return m.group(0)
    return None


def _raw_header(header_spans: list[dict]) -> str | None:
    """Header/stage text: header-band spans minus the module name, trait words and '6+1'."""
    parts: list[str] = []
    for s in header_spans:
        low = s["text"].lower()
        if low in _MODULES_LOWER or low in TRAITS or "6+1" in low:
            continue
        parts.append(s["text"])
    header = " ".join(parts).strip()
    return header or None


def _activity_title(body_spans: list[dict], centre_x: float, width: float) -> str | None:
    """First bold, centred body line — the strongest tie-breaker on shared metadata."""
    tol = CENTRE_TOL * width
    for s in body_spans:
        if s["bold"] and abs(s["cx"] - centre_x) < tol:
            return s["text"]
    return None


def _writing_traits(spans: list[dict], content_md: str) -> list[str]:
    """6+1 traits, lowercased. Gated on the box label, collected positionally near it.

    Only pages carrying the '6+1 Writing Traits' box contribute traits (~63% of the corpus);
    trait words are gathered from spans within TRAITS_BOX_SPAN*H below the label so body prose
    that merely mentions a trait word does not leak in. Empty list if the box is absent.
    """
    label_ys = [s["y"] for s in spans if TRAITS_BOX_LABEL.lower() in s["text"].lower()]
    if not label_ys:
        return []
    top = min(label_ys)
    found: set[str] = set()
    for s in spans:
        if top - 0.02 <= s["y"] <= top + TRAITS_BOX_SPAN:
            low = s["text"].lower()
            for trait in TRAITS:
                if trait in low:
                    found.add(trait)
    return sorted(found)
