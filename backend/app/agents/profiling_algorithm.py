"""ProfilingAlgorithm - Subsystem 2 core.

Analyses assessment records into ProfileMetrics; clusters the cohort to group
learners. Deterministic (not the LLM) per the class diagram.

Scoring: each task in `assessment_records.task_results` is normalised to
score/max_score, mapped to the cognitive dimension(s) it evidences, and averaged.
Records are read newest-first and the first record carrying evidence for a
dimension wins, so a learner's current ability is not diluted by older sittings.

Clustering (`cluster`) is a separate concern on separate data: k-means over the six
literacy skills in `learner_scores`, one row per student. It answers "which learners
look like each other" for the cohort scatter, where `analyse` answers "how is this
one learner doing" for the radar chart.
"""
from __future__ import annotations

from dataclasses import dataclass, field

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


class NoPatternError(Exception):
    """The records evidenced nothing at all, so there is no profile to build.

    The `NoPatternError` branch of the UC2 sequence diagram (UT-2.9, IT-2.6, ST-2.3).

    Raised only when NOT ONE dimension could be scored — no records, every task name
    unrecognised, or every task unscorable. A partially-evidenced set is not an error:
    the dimensions that were evidenced keep their scores and the rest sit at NEUTRAL,
    which is the point of NEUTRAL.

    The distinction matters clinically. "We scored three of seven dimensions" is a usable
    profile a therapist can act on; "we scored none" is a seven-way NEUTRAL reading that
    looks like a real result and is not — every dimension would render at exactly 50% on
    the radar chart, which is a statement about our parser, not about the learner.
    """

# ── Clustering ───────────────────────────────────────────────────────────────
# k is not a parameter of the system: it is chosen per run as the k with the best
# silhouette score. The sweep runs k = 2..10 — 1 is not a clustering, and past ~10 the
# groups stop being something a therapist can hold in their head (and the legend stops
# fitting on the dashboard).
K_MIN, K_MAX = 2, 10

# Fixed so the same workbook always yields the same labels. Without it k-means' random
# init would reshuffle which learner sits in which cluster on every re-ingest, and the
# colours on the dashboard would change for no reason the therapist can see.
RANDOM_STATE = 42

# Silhouette is O(n^2) in distance computations. At the cohort's ~5.8k rows that is ~34M
# pairs per k, nine times over — minutes, for a number we only compare against eight
# others. Scoring a fixed random subsample is the standard remedy and preserves the
# ranking; the sample is seeded by RANDOM_STATE, so the choice of k stays reproducible.
SILHOUETTE_SAMPLE = 3000

# Smallest group `cluster_by_group` will fit. Below this, "clusters" are describing individual
# learners rather than patterns — the workbook's 3 unbanded students would otherwise get their
# own two-cluster model. They are left unlabelled and reported as unclustered instead.
MIN_GROUP = 30


@dataclass(frozen=True)
class ClusterRun:
    """One k-means fit over one feature tier, plus the evidence for why this k.

    `labels` is keyed by whatever identifier the caller put in each row's `id_key`, so this
    class never needs to know that the cohort is identified by an anonymised student id.
    """
    tier: str
    features: tuple[str, ...]
    k: int
    best_silhouette: float
    silhouette_by_k: dict[int, float]
    labels: dict[str, str]
    centroids: list[dict] = field(default_factory=list)
    n_learners: int = 0
    n_skipped: int = 0


class ProfilingAlgorithm:
    def analyse(self, records: list[dict]) -> dict:
        """records -> ProfileMetrics (the seven cognitive dimensions), each 0.0-1.0.

        Raises NoPatternError when no dimension could be scored at all — see that class
        for why a fully-NEUTRAL result is refused rather than returned.
        """
        scores: dict[str, float] = {}

        for record in self._newest_first(records or []):
            for dimension, ratios in self._dimension_ratios(record).items():
                # First record with evidence for this dimension wins; later (older)
                # records only fill dimensions still unscored.
                if dimension not in scores and ratios:
                    scores[dimension] = round(sum(ratios) / len(ratios), 4)

        if not scores:
            raise NoPatternError(
                f"No profile dimension could be scored from {len(records or [])} record(s)."
            )

        return {dim: scores.get(dim, NEUTRAL) for dim in DIMENSIONS}

    def cluster(
        self,
        rows: list[dict],
        features: tuple[str, ...],
        tier: str,
        id_key: str = "student_id",
        k_min: int = K_MIN,
        k_max: int = K_MAX,
    ) -> ClusterRun | None:
        """k-means the cohort over `features`, picking k by silhouette score.

        `rows` is one dict per learner. Rows missing any of `features` are dropped rather
        than imputed: three of the six literacy skills are absent for a third of the cohort,
        and Exposition/Persuasive Writing are 87%/97% zero, so a filled-in value would be an
        invention rather than an estimate. The caller sees how many were dropped in
        `n_skipped` and the dashboard reports it.

        Returns None when fewer than k_min + 1 rows survive — there is nothing to partition,
        and that is a legitimate state (an empty database), not an error.

        Pure: no repository, no I/O, no global state. Same rows in, same labels out.
        """
        import numpy as np
        from sklearn.cluster import KMeans
        from sklearn.metrics import silhouette_score
        from sklearn.preprocessing import StandardScaler

        usable = [r for r in rows if self._has_all(r, features)]
        n_skipped = len(rows) - len(usable)
        if len(usable) <= k_min:
            return None

        matrix = np.array([[float(r[f]) for f in features] for r in usable], dtype=float)

        # MANDATORY, not a nicety. The raw features live on different scales — Phonics runs
        # 0-46 while Word Reading runs 0-10 — and k-means minimises Euclidean distance, so
        # without this the partition is decided by Phonics alone and the other five skills
        # contribute noise. The notebook shows the two fits side by side.
        scaled = StandardScaler().fit_transform(matrix)

        # Never ask for more clusters than there are distinct points: k-means would return
        # empty clusters and silhouette_score would raise.
        upper = min(k_max, len(np.unique(scaled, axis=0)) - 1)
        if upper < k_min:
            return None

        silhouette_by_k: dict[int, float] = {}
        fits: dict[int, "KMeans"] = {}
        for k in range(k_min, upper + 1):
            model = KMeans(n_clusters=k, n_init=10, random_state=RANDOM_STATE).fit(scaled)
            fits[k] = model
            silhouette_by_k[k] = float(
                silhouette_score(
                    scaled,
                    model.labels_,
                    sample_size=min(SILHOUETTE_SAMPLE, len(scaled)),
                    random_state=RANDOM_STATE,
                )
            )

        best_k = max(silhouette_by_k, key=silhouette_by_k.get)
        model = fits[best_k]

        # k-means numbers its clusters by initialisation order, which carries no meaning.
        # Re-rank them by centroid mean (in scaled space, so every skill counts equally):
        # "<Tier> 1" is then always the lowest-scoring group and "<Tier> k" the highest, and
        # the dashboard legend — which sorts its labels — reads low to high.
        order = np.argsort(model.cluster_centers_.mean(axis=1))
        rank = {int(original): position + 1 for position, original in enumerate(order)}

        # Zero-padded to the width of k, because the legend and the table sort these labels
        # as text: at k=10, an unpadded "Core 10" would sort between "Core 1" and "Core 2"
        # and the low-to-high reading would be lost. Below k=10 the width is 1, so the
        # common case still reads "Core 1".
        width = len(str(best_k))
        def name(raw: int) -> str:
            return f"{tier} {rank[int(raw)]:0{width}d}"

        labels = {str(row[id_key]): name(raw) for row, raw in zip(usable, model.labels_)}

        # Centroids in ORIGINAL units, not scaled ones: "Phonics 31.4" is something a
        # therapist can read, "Phonics 0.64 sd above the mean" is not.
        centroids = []
        for raw in range(best_k):
            member = model.labels_ == raw
            centroids.append({
                "cluster": name(raw),
                "n": int(member.sum()),
                **{f: round(float(matrix[member, i].mean()), 2)
                   for i, f in enumerate(features)},
            })
        centroids.sort(key=lambda c: c["cluster"])

        return ClusterRun(
            tier=tier,
            features=tuple(features),
            k=best_k,
            best_silhouette=round(silhouette_by_k[best_k], 4),
            silhouette_by_k={k: round(v, 4) for k, v in silhouette_by_k.items()},
            labels=labels,
            centroids=centroids,
            n_learners=len(usable),
            n_skipped=n_skipped,
        )

    def cluster_by_group(
        self,
        rows: list[dict],
        features: tuple[str, ...],
        group_key: str,
        min_group: int = MIN_GROUP,
        **kwargs,
    ) -> dict[str, ClusterRun]:
        """One independent `cluster()` per distinct value of `rows[group_key]`.

        Used to fit each band group separately, because the assessment papers — and therefore
        the score scales — differ between bands; see `app.ingestion.dial_workbook`.

        Groups smaller than `min_group`, and groups too small to partition at all, are skipped:
        the caller gets no key for them and must treat that as "these learners have no label"
        rather than an error. The dashboard reports them as unclustered.

        The group value becomes the label prefix: group "A" yields "A 1" ... "A k". Because
        each group is fitted alone, its k is chosen on its own silhouette curve — band A can
        land on k=5 while band C lands on k=2.
        """
        groups: dict[str, list[dict]] = {}
        for row in rows:
            groups.setdefault(str(row.get(group_key)), []).append(row)

        runs = {}
        for name in sorted(groups):
            if len(groups[name]) < min_group:
                continue
            run = self.cluster(groups[name], features, tier=name, **kwargs)
            if run is not None:
                runs[name] = run
        return runs

    # ── helpers ───────────────────────────────────────────────────────────
    @staticmethod
    def _has_all(row: dict, features: tuple[str, ...]) -> bool:
        """Every feature present and numeric.

        Coerces rather than isinstance-checking: these rows come out of pandas, where an
        integer column yields numpy.int64 — which is NOT a subclass of int, so an isinstance
        gate would silently discard the entire cohort. NaN is the pandas spelling of a blank
        cell and counts as absent (`x != x` is true only for NaN)."""
        for f in features:
            value = row.get(f)
            if value is None or isinstance(value, bool):
                return False
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                return False
            if numeric != numeric:  # NaN
                return False
        return True

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
