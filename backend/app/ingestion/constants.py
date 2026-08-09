"""Static curriculum taxonomy driving deterministic ingestion.

Everything here is *data*, not logic — the parsers and normalise.py read these tables so the
chunking stays deterministic and diffable. No LLM, no heuristics beyond these maps.

NOTE ON THE CONCEPT TAXONOMY
    The two modules and the stage/trait vocabularies below are measured facts from the spec
    (validated against all 14 books). The *concept* set is the seed taxonomy the corpus is
    known to teach; concepts are detected from PDF headings via carry-forward, so a heading
    that is not yet listed still parses (it becomes its own concept key). Reconcile CONCEPTS /
    CONCEPT_TO_MODULE / PREREQUISITES against the `run --all --dry-run` output (build step 10)
    once the PDFs are in place, and extend as new books are confirmed.
"""
from __future__ import annotations

# ── Modules ──────────────────────────────────────────────────────────────────
# The two header top-left modules (measured: exactly two across the corpus).
BAREBONE_SENTENCE = "Barebone Sentence"
PREDICATE_EXPANDERS = "Predicate Expanders"
MODULES: tuple[str, ...] = (BAREBONE_SENTENCE, PREDICATE_EXPANDERS)

# Sentinel concept for pages that teach no single concept (review/summary/word-list/etc.).
CONCEPT_ALL = "all"

# ── Concepts (seed taxonomy — see module docstring) ──────────────────────────
CONCEPTS: tuple[str, ...] = (
    # Barebone Sentence module (sentence construction)
    "subject",
    "action_predicate",
    # Predicate Expanders module
    "predicate_expander",
    "compound",
    "series",
    # Band books A1–A3 (phonics / oracy)
    "phonemic_awareness",
    "alphabet_knowledge",
    "oracy",
    # sentinel
    CONCEPT_ALL,
)

# concept -> owning module. Band-book / phonics concepts have no module (None).
CONCEPT_TO_MODULE: dict[str, str] = {
    "subject": BAREBONE_SENTENCE,
    "action_predicate": BAREBONE_SENTENCE,
    "predicate_expander": PREDICATE_EXPANDERS,
    "compound": PREDICATE_EXPANDERS,
    "series": PREDICATE_EXPANDERS,
}

# Scope-and-sequence as data — the validator checks a chunk's concept against these.
# concept -> concepts that must be taught first.
PREREQUISITES: dict[str, list[str]] = {
    "action_predicate": ["subject"],
    "predicate_expander": ["action_predicate"],
    "compound": ["action_predicate"],
    "series": ["action_predicate"],
}

# ── Cognitive-construct bridge ───────────────────────────────────────────────
# Free-text construct tags on a curriculum chunk. Written against the seven derived
# dimensions that no longer exist; retrieval filters on band/concept/stage regardless.
# HONEST mapping only. Band-book/phonics concepts map to the constructs the spec names;
# Project Read grammar concepts have no clean mapping and stay EMPTY. Do NOT invent mappings —
# an empty array is more honest than a wrong one. The seven constructs are:
#   phonological_processing, decoding, spelling, comprehension,
#   working_memory, executive_functioning, visualisation
CONCEPT_TO_CONSTRUCTS: dict[str, list[str]] = {
    "phonemic_awareness": ["phonological_processing"],
    "alphabet_knowledge": ["decoding"],
    "oracy": ["visualisation"],
    # subject / action_predicate / predicate_expander / compound / series / all -> [] (omitted)
}

# ── Stage vocabulary ─────────────────────────────────────────────────────────
# Canonical stage enum (normalise never returns None — it falls back to the cleaned header).
CANONICAL_STAGES: frozenset[str] = frozenset({
    "presentation",
    "introduction",
    "practice",
    "production",
    "production_activity",
    "resources",
    "extended",
    "wordlist",
    "review",
    "summary",
    "game",
})

# Ordered header-pattern -> canonical stage. normalise.py matches these against the cleaned,
# lowercased header IN ORDER, so more specific patterns MUST come first
# ("production activity" before "production", "introduction worksheet" before "introduction").
STAGE_MAP: dict[str, str] = {
    "presentation": "presentation",
    "introduction worksheet": "introduction",
    "introduction": "introduction",
    "practice worksheet": "practice",
    "practice": "practice",
    "production activity": "production_activity",
    "production": "production",
    "resources": "resources",
    "resource": "resources",
    "extended": "extended",
    "word list": "wordlist",
    "wordlist": "wordlist",
    "review": "review",
    "summary": "summary",
    "game": "game",
}

# Stages that teach no single concept: reset the carry-forward to CONCEPT_ALL, never inherit.
CONCEPT_RESET_STAGES: frozenset[str] = frozenset({
    "review", "summary", "wordlist", "extended",
})

# Resource / cut-out ("Barebones") pages -> doc_type='resource' (excluded from retrieval).
RESOURCE_STAGES: frozenset[str] = frozenset({"resources"})

# ── 6+1 Writing Traits ───────────────────────────────────────────────────────
# Recognised trait vocabulary, lowercased (corpus has both 'Word choice' and 'Word Choice',
# and uses 'sentence structure' where classic 6+1 says 'sentence fluency'). Empty if absent.
TRAITS: frozenset[str] = frozenset({
    "ideas",
    "organization",
    "organisation",
    "voice",
    "word choice",
    "sentence fluency",
    "sentence structure",
    "conventions",
    "presentation",
})

# Label that marks the 6+1 box in the page text (used positionally, not grepped for headers).
TRAITS_BOX_LABEL = "6+1 Writing Traits"
