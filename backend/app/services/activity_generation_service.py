"""ActivityGenerationService - Subsystem 3 orchestration.

Curriculum-grounded RAG, the same flow `scripts.generate_activity` runs from the CLI:

    learner_profiles row -> retrieval query -> curriculum_chunks (hybrid RRF)
      -> similarity gate -> guardrailed prompt -> LLM -> learning_activities row

The learner's profile IS the input. The caller passes an id, never scores, so the
query is always derived server-side from the stored profile.
"""
from app.repositories.learner_profile_repository import LearnerProfileRepository
from app.repositories.activity_repository import ActivityRepository
from app.services.curriculum_retrieval_service import CurriculumRetrievalService
from app.gateways.llm_client import LLMApiClient
from app.prompts.activity_prompts import (
    INSUFFICIENT_CONTEXT, MIN_SIMILARITY, SYSTEM_PROMPT,
    build_activity_prompt, model_refused, top_similarity,
)

# The seven cognitive dimensions ProfilingAlgorithm scores — these are columns on
# learner_profiles, not free-form keys, so the ordering below is stable.
PROFILE_DIMENSIONS = (
    "phonological_processing", "decoding", "spelling", "comprehension",
    "working_memory", "executive_functioning", "visualisation",
)
WEAKEST_N = 2  # how many low-scoring dimensions steer the retrieval query


class ActivityGenerationService:
    def __init__(self):
        self.profiles = LearnerProfileRepository()
        self.activities = ActivityRepository()
        self.curriculum = CurriculumRetrievalService()
        self.llm = LLMApiClient()

    # ── profile ───────────────────────────────────────────────────────────
    def load_profile(self, profile_id: str) -> dict | None:
        """Resolve the route param against learner_profiles.

        Tried as a profile id first, then as a learner id: the dashboard's Generate
        page only has the learner it put on screen, while /profiles/{id}/activities
        deals in profile ids. Both reach the same row.
        """
        return (
            self.profiles.find_by_id(profile_id)
            or self.profiles.find_by_learner(profile_id)
        )

    def build_query(self, profile: dict | None, params: dict) -> str:
        """Turn a profile into the retrieval query: target what the learner is weakest at.

        Scores are 0-1 (higher = stronger), so the lowest dimensions are the need. Any
        `notes` from the caller are appended as a steer rather than replacing the profile.
        """
        parts: list[str] = []

        scored = [
            (dim, profile[dim]) for dim in PROFILE_DIMENSIONS
            if profile and isinstance(profile.get(dim), (int, float))
        ]
        if scored:
            scored.sort(key=lambda kv: kv[1])
            weakest = [dim.replace("_", " ") for dim, _ in scored[:WEAKEST_N]]
            parts.append("literacy activity targeting " + " and ".join(weakest))

        for extra in (params.get("literacy_objective"), params.get("notes")):
            if extra:
                parts.append(extra)

        # No profile scores and no steer: deliberately left thin so the similarity
        # gate below refuses rather than the LLM inventing from a generic query.
        return " — ".join(parts)

    # ── generation ────────────────────────────────────────────────────────
    def generate(self, profile_id: str, params: dict) -> dict:
        profile = self.load_profile(profile_id)
        query = self.build_query(profile, params)

        chunks = self.curriculum.retrieve(
            query,
            band=params.get("band") or params.get("level") or None,
            concept=params.get("concept"),
            stage=params.get("stage"),
            k=params.get("k") or 3,
        )

        # Guardrail 1 — refuse before spending an LLM call when grounding is thin.
        best = top_similarity(chunks)
        if not chunks or best is None or best < MIN_SIMILARITY:
            return self._refusal(profile_id, query, chunks, best)

        prompt = build_activity_prompt(chunks, self._request_params(params), profile)
        text = self.llm.complete(prompt, system=SYSTEM_PROMPT)

        # Guardrail 2 — the model can still self-refuse past the similarity gate
        # (an off-topic request whose generic tokens sneak over the threshold).
        if model_refused(text):
            return self._refusal(profile_id, query, chunks, best, model_text=text)

        activity = {
            "profiled": profile["id"] if profile else None,
            "content": {"text": text, "query": query},
            "literacy_objective": params.get("literacy_objective", ""),
            "level": params.get("level") or params.get("band") or "",
            "status": "GENERATED",
            "grounded_on": [self._chunk_label(c) for c in chunks],
        }
        self.activities.save(activity)

        return {
            "status": "GENERATED",
            "content": text,
            "query": query,
            "grounding": [self._chunk_summary(c) for c in chunks],
            "profile_id": profile["id"] if profile else None,
        }

    def list_activities(self, profile_id: str) -> list[dict]:
        return self.activities.find_by_profile(profile_id)

    # ── helpers ───────────────────────────────────────────────────────────
    def _request_params(self, params: dict) -> dict:
        """The filters/notes the prompt should echo back — retrieval knobs like `k`
        are ours, not the model's business."""
        keys = ("band", "concept", "stage", "level", "literacy_objective", "notes")
        return {k: params[k] for k in keys if params.get(k)}

    def _refusal(self, profile_id, query, chunks, best, model_text=None) -> dict:
        """INSUFFICIENT_CONTEXT response. Not persisted — a refusal is not an activity."""
        if model_text is not None:
            reason = "The model judged the retrieved curriculum insufficient for this request."
        else:
            score = f"{best:.3f}" if isinstance(best, (int, float)) else "none"
            reason = (
                f"Retrieved {len(chunks)} curriculum chunk(s); best similarity {score} "
                f"is below the {MIN_SIMILARITY} gate. Loosen the filters or ingest more "
                f"curriculum for this profile's needs."
            )
        return {
            "status": INSUFFICIENT_CONTEXT,
            "content": (model_text or "").strip(),
            "reason": reason,
            "query": query,
            "grounding": [self._chunk_summary(c) for c in chunks],
            "profile_id": profile_id,
        }

    def _chunk_label(self, chunk: dict) -> str:
        """Compact provenance string for learning_activities.grounded_on (text[])."""
        title = chunk.get("activity_title") or "(untitled)"
        return f"{title} ({chunk.get('source_file') or '?'} p.{chunk.get('page_start') or '?'})"

    def _chunk_summary(self, chunk: dict) -> dict:
        """Grounding row the frontend renders under the activity, so a therapist can
        see which curriculum pages it came from."""
        return {
            "title": chunk.get("activity_title") or "(untitled)",
            "source": chunk.get("source_file"),
            "page": chunk.get("page_start"),
            "concept": chunk.get("concept"),
            "stage": chunk.get("stage"),
            "similarity": chunk.get("similarity"),
        }
