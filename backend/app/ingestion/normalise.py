"""Deterministic normalisation — turns raw page signals into stable segmentation keys.

REQUIRED before comparing anything, or chunks break. Pure functions, no I/O: same input ->
same output. Order per the spec:

    1. unicode fold (curly vs straight quotes are visually identical, unequal as strings)
    2. strip parenthetical suffixes before comparing stages
    3. extract sequence_no from the trailing digit (default 1)
    4. map header -> canonical stage, with a FALLBACK to the cleaned header — NEVER None
    5. concept carry-forward (switch only on an explicit heading; reset on review/summary/etc.)
    6. writing traits: lowercase + validate
    7. activity_title: fold + collapse whitespace
"""
from __future__ import annotations
import re

from app.ingestion.constants import (
    CONCEPT_ALL,
    CONCEPT_RESET_STAGES,
    STAGE_MAP,
    TRAITS,
)

# 1. Unicode fold — the corpus mixes U+2019/U+0027 etc. on otherwise-identical titles.
_UNICODE_FOLD = {
    "’": "'", "‘": "'",       # curly single quotes
    "“": '"', "”": '"',       # curly double quotes
    "–": "-", "—": "-",       # en/em dash
    " ": " ",                       # non-breaking space
    "…": "...",                     # ellipsis
}
_UNICODE_RE = re.compile("|".join(re.escape(k) for k in _UNICODE_FOLD))

_PAREN_RE = re.compile(r"\([^)]*\)")     # parenthetical suffixes
_TRAILING_INT_RE = re.compile(r"(\d+)\s*$")
_WS_RE = re.compile(r"\s+")

# Concept heading -> canonical concept. Matched ONLY against heading/title text a parser feeds
# in (never body prose), so a body mention of "compound" does not switch the concept state.
# Ordered: more specific patterns first.
_CONCEPT_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("action predicate", "action_predicate"),
    ("predicate expander", "predicate_expander"),
    ("expander", "predicate_expander"),
    ("compound", "compound"),
    ("series", "series"),
    ("subject", "subject"),
    ("phonemic", "phonemic_awareness"),
    ("phoneme", "phonemic_awareness"),
    ("alphabet", "alphabet_knowledge"),
    ("oracy", "oracy"),
)


def fold_unicode(text: str) -> str:
    """Replace visually-identical unicode variants with their ASCII form."""
    return _UNICODE_RE.sub(lambda m: _UNICODE_FOLD[m.group(0)], text)


def clean_text(text: str | None) -> str:
    """Fold unicode and collapse runs of whitespace."""
    if not text:
        return ""
    return _WS_RE.sub(" ", fold_unicode(text)).strip()


def strip_parentheticals(text: str) -> str:
    """Drop '(Band A1-A3)' / '(Suggested Answers)' etc. so they don't split a stage."""
    return _WS_RE.sub(" ", _PAREN_RE.sub("", text)).strip()


def extract_sequence_no(text: str) -> int:
    """Trailing integer -> sequence_no; default 1 (Practice worksheet 1 vs 2 vs 3)."""
    m = _TRAILING_INT_RE.search(text)
    return int(m.group(1)) if m else 1


def normalise_stage(raw_header: str | None) -> tuple[str, int]:
    """(canonical stage, sequence_no). Stage is NEVER None — falls back to the cleaned header.

    'Practice worksheet 1 (Band A1-A3)'        -> ('practice', 1)
    'Practice worksheet 1 (Suggested Answers)' -> ('practice', 1)   (same chunk as above)
    'Practice worksheet 2'                     -> ('practice', 2)   (different chunk)
    'A Writing Game!'                          -> ('game', 1)
    "Let's recall!"                            -> ("let's recall!", 1)   (fallback, folded)
    """
    cleaned = strip_parentheticals(fold_unicode(raw_header or "")).strip()
    seq = extract_sequence_no(cleaned)
    low = cleaned.lower()
    for pattern, canonical in STAGE_MAP.items():   # insertion order = specificity
        if pattern in low:
            return canonical, seq
    return (low or "unknown"), seq                 # fallback, never None


def detect_concept(heading: str | None) -> str | None:
    """Map an explicit concept heading/title to a canonical concept, else None.

    Feed ONLY heading/title text (e.g. a presentation page's activity_title). Returning None
    means "no explicit concept here" -> the caller carries the previous concept forward.
    """
    if not heading:
        return None
    low = fold_unicode(heading).lower()
    for keyword, concept in _CONCEPT_KEYWORDS:
        if keyword in low:
            return concept
    return None


def resolve_concept(prev: str | None, heading: str | None, stage: str) -> str:
    """Carry-forward state machine for concept.

    - review / summary / word-list / generic extended -> CONCEPT_ALL (do NOT inherit)
    - an explicit concept heading -> switch to it
    - otherwise -> carry the previous concept forward (CONCEPT_ALL until the first heading)
    """
    if stage in CONCEPT_RESET_STAGES:
        return CONCEPT_ALL
    explicit = detect_concept(heading)
    if explicit:
        return explicit
    return prev if prev is not None else CONCEPT_ALL


def normalise_traits(traits: list[str] | None) -> list[str]:
    """Lowercase, keep only recognised 6+1 traits, dedup, sort. Empty list if none."""
    if not traits:
        return []
    return sorted({t.lower() for t in traits if t.lower() in TRAITS})


def normalise_title(text: str | None) -> str | None:
    """Fold + collapse whitespace on a body heading; None if empty."""
    cleaned = clean_text(text)
    return cleaned or None
