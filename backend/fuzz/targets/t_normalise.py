"""Target for `app/ingestion/normalise.py` — the second target our PM3 plan named.

The plan's rationale was "136 lines of pure string transforms with zero tests", which is exactly
the profile a fuzzer is good at: no I/O to stub, no state to set up, and every function is a
total function over `str` whose contract is written in its own docstring.

The oracles below are those docstrings turned into assertions:

    fold_unicode      "Replace visually-identical unicode variants with their ASCII form"
                      -> folding twice must equal folding once, or the fold is not a normal form.
    clean_text        "Fold unicode and collapse runs of whitespace"
                      -> the output must contain no whitespace run and no outer whitespace.
    normalise_stage   "Stage is NEVER None - falls back to the cleaned header"
                      -> the stage is always a non-empty string.
    normalise_traits  "keep only recognised 6+1 traits, dedup, sort"
                      -> output is a sorted, duplicate-free subset of TRAITS.
    normalise_title   "None if empty"
                      -> the result is None or a non-empty string, never "".
"""
from __future__ import annotations

from app.ingestion.constants import TRAITS
from app.ingestion.normalise import (
    clean_text,
    detect_concept,
    extract_sequence_no,
    fold_unicode,
    normalise_stage,
    normalise_title,
    normalise_traits,
    resolve_concept,
    strip_parentheticals,
)
from fuzz.oracles import invariant
from fuzz.targets.base import Target, as_text, register

# Real headers from the curriculum layout, plus the shapes the docstring's own examples name.
SEED_HEADERS = [
    b"Practice worksheet 1 (Band A1-A3)",
    b"Practice worksheet 1 (Suggested Answers)",
    b"Practice worksheet 2",
    b"A Writing Game!",
    b"Let's recall!",
    b"Compound Words \xe2\x80\x93 Predicate Expander 3",
    b"Phonemic Awareness Review",
    b"Alphabet Knowledge (Band A1)",
    b"",
]


@register
class NormaliseTarget(Target):
    name = "normalise"
    #: Every function here is documented as total. Nothing is allowed to raise, so an empty
    #: `allowed` tuple means ANY exception is a finding.
    allowed = ()
    oracles = ("crash", "hang", "invariant")
    max_size = 32768

    def seeds(self) -> list[bytes]:
        return list(SEED_HEADERS)

    def run(self, data: bytes) -> None:
        text = as_text(data)

        # fold_unicode must be a normal form: applying it again changes nothing.
        folded = fold_unicode(text)
        invariant(
            fold_unicode(folded) == folded,
            "fold_unicode is not idempotent",
        )

        # clean_text must actually collapse whitespace and trim.
        cleaned = clean_text(text)
        invariant(
            "  " not in cleaned,
            f"clean_text left a double space in {cleaned[:80]!r}",
        )
        invariant(
            cleaned == cleaned.strip(),
            f"clean_text left outer whitespace in {cleaned[:80]!r}",
        )
        invariant(
            clean_text(cleaned) == cleaned,
            "clean_text is not idempotent",
        )

        strip_parentheticals(text)

        # extract_sequence_no is documented as "trailing integer -> sequence_no; default 1".
        seq = extract_sequence_no(text)
        invariant(isinstance(seq, int), f"extract_sequence_no returned {type(seq).__name__}")
        invariant(seq >= 0, f"extract_sequence_no returned a negative sequence {seq}")

        # normalise_stage promises a stage that is NEVER None, and a sequence alongside it.
        stage, stage_seq = normalise_stage(text)
        invariant(isinstance(stage, str) and stage != "", "normalise_stage returned an empty stage")
        invariant(isinstance(stage_seq, int), "normalise_stage returned a non-int sequence")

        # detect_concept returns a canonical concept or None; resolve_concept is total.
        concept = detect_concept(text)
        invariant(
            concept is None or isinstance(concept, str),
            f"detect_concept returned {concept!r}",
        )
        resolved = resolve_concept(None, text, stage)
        invariant(isinstance(resolved, str), f"resolve_concept returned {resolved!r}")

        # normalise_traits: a sorted, deduplicated subset of the recognised traits.
        candidate_traits = [chunk for chunk in text.split(",") if chunk][:32]
        traits = normalise_traits(candidate_traits)
        invariant(
            set(traits) <= set(TRAITS),
            f"normalise_traits returned values outside TRAITS: {set(traits) - set(TRAITS)}",
        )
        invariant(
            traits == sorted(set(traits)),
            f"normalise_traits returned {traits!r}, which is not sorted and unique",
        )

        # normalise_title: None or a non-empty string, never "".
        title = normalise_title(text)
        invariant(
            title is None or (isinstance(title, str) and title != ""),
            f"normalise_title returned {title!r}",
        )
