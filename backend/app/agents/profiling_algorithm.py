"""ProfilingAlgorithm - Subsystem 2 core.

Analyses assessment records into ProfileMetrics; optional clustering to
group learners. Deterministic (not the LLM) per the class diagram.

Scoring: each task in `assessment_records.task_results` is normalised to
score/max_score, mapped to the cognitive dimension(s) it evidences, and averaged.
Records are read newest-first and the first record carrying evidence for a
dimension wins, so a learner's current ability is not diluted by older sittings.
"""
from __future__ import annotations

# The seven dimensions, matching the learner_profiles columns. analyse() must return
# exactly these keys — ProfilingService writes the dict straight to the table, so an
# extra key is an "column does not exist" error from Supabase.
DIMENSIONS = (
    "phonological_processing", "decoding", "spelling", "comprehension",
    "working_memory", "executive_functioning", "visualisation",
)

# Task-name -> dimension routing. DAS reports name subtests in prose ("Phoneme
# Segmentation", "Rapid Automatised Naming"), so match on lowercased substrings
# rather than exact keys. A task may evidence more than one dimension; every match
# contributes. NOTE: this mapping is an engineering approximation and wants a
# clinician's sign-off before it drives real caseload decisions.
DIMENSION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "phonological_processing": ("phonem", "phonolog", "rhyme", "syllab", "blend", "segment", "sound"),
    "decoding": ("decod", "nonword", "non-word", "pseudoword", "word read", "word attack",
                 "grapheme", "letter", "fluenc"),
    # No bare "writ" here: it swallows "Handwriting", which measures motor skill,
    # not spelling. Real spelling subtests say so ("Written Spelling") or "dictation".
    "spelling": ("spell", "dictation"),
    "comprehension": ("comprehen", "vocabular", "listening", "passage", "inferen", "meaning"),
    "working_memory": ("memory", "digit span", "digit", "recall", "span", "repetition"),
    "executive_functioning": ("executive", "attention", "planning", "inhibit", "shift",
                              "rapid", "naming speed", "automatis", "automatiz"),
    "visualisation": ("visual", "orthograph", "copy", "shape", "symbol"),
}

NEUTRAL = 0.5  # used for a dimension no assessment task evidences


class ProfilingAlgorithm:
    def analyse(self, records: list[dict]) -> dict:
        """records -> ProfileMetrics (the seven cognitive dimensions), each 0.0-1.0."""
        scores: dict[str, float] = {}

        for record in self._newest_first(records or []):
            for dimension, ratios in self._dimension_ratios(record).items():
                # First record with evidence for this dimension wins; later (older)
                # records only fill dimensions still unscored.
                if dimension not in scores and ratios:
                    scores[dimension] = round(sum(ratios) / len(ratios), 4)

        return {dim: scores.get(dim, NEUTRAL) for dim in DIMENSIONS}

    def cluster(self, records: list[dict]) -> list[list[dict]]:
        return [records]

    # ── helpers ───────────────────────────────────────────────────────────
    def _newest_first(self, records: list[dict]) -> list[dict]:
        """Sort by assessment_date descending. Dates are ISO strings, so a string
        sort is chronological; a missing date sorts last rather than raising."""
        return sorted(records, key=lambda r: str(r.get("assessment_date") or ""), reverse=True)

    def _dimension_ratios(self, record: dict) -> dict[str, list[float]]:
        """One record's task_results as {dimension: [normalised scores]}."""
        buckets: dict[str, list[float]] = {}

        for name, result in (record.get("task_results") or {}).items():
            ratio = self._ratio(result)
            if ratio is None:
                continue
            for dimension in self._dimensions_for(name):
                buckets.setdefault(dimension, []).append(ratio)

        return buckets

    def _ratio(self, result) -> float | None:
        """score/max_score clamped to 0-1. Accepts the parser's
        {"score": n, "max_score": m} shape or a bare already-normalised number."""
        if isinstance(result, (int, float)) and not isinstance(result, bool):
            return min(max(float(result), 0.0), 1.0)
        if not isinstance(result, dict):
            return None

        score, maximum = result.get("score"), result.get("max_score")
        if not isinstance(score, (int, float)) or not isinstance(maximum, (int, float)):
            return None
        if maximum <= 0:  # guard: an unscored row must not divide by zero
            return None
        return min(max(score / maximum, 0.0), 1.0)

    def _dimensions_for(self, task_name: str) -> list[str]:
        """Every dimension whose keywords appear in the task name. Unrecognised
        tasks map to nothing and are simply ignored — better than mis-attributing."""
        lowered = str(task_name).lower()
        return [dim for dim, keywords in DIMENSION_KEYWORDS.items()
                if any(keyword in lowered for keyword in keywords)]
