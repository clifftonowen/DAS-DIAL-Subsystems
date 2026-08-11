"""ActivityGenerationService - Subsystem 3 orchestration.

Curriculum-grounded RAG feeding a generate/validate loop:

    learner's DIAL marks -> retrieval query -> curriculum_chunks (hybrid RRF)
      -> similarity gate -> guardrailed prompt
      -> ActivityGraph [write -> review -> reprompt with notes]
      -> learning_activities row (VALIDATED or FLAGGED)

The learner's profile IS the input. The caller passes an id, never scores, so the
query is always derived server-side from the stored profile.

NOTE: `scripts.generate_activity` still runs the pre-loop single-shot flow for ad-hoc CLI use.
It shares the prompts and the gate but not the reviewer, so its output is a draft — nothing it
prints has been validated, and it writes no row.
"""
from app.agents.activity_graph import ActivityGraph
from app.ingestion.dial_features import (
    FEATURE_LABELS, PLOT_FEATURES, UNBANDED, normalised_score,
)
from app.repositories.learner_repository import LearnerRepository
from app.repositories.activity_repository import ActivityRepository
from app.repositories.curriculum_repository import CurriculumRepository
from app.services.curriculum_retrieval_service import CurriculumRetrievalService
from app.prompts.activity_prompts import (
    INSUFFICIENT_CONTEXT, MIN_SIMILARITY, SYSTEM_PROMPT,
    build_activity_prompt, model_refused, top_similarity,
)

# The four DIAL marks, which ARE the learner's profile — columns on `learners`, not free-form
# keys, so the ordering is stable. Replaced the seven derived cognitive dimensions.
WEAK_THRESHOLD = 5.0  # a normalised score below this is a skill worth targeting


class ActivityGenerationService:
    def __init__(self):
        self.learners = LearnerRepository()
        self.activities = ActivityRepository()
        self.curriculum = CurriculumRetrievalService()
        self.chunks = CurriculumRepository()   # corpus counts, for honest refusal reasons only
        # The ONLY LLM edge in UC3. The service no longer holds a client of its own: generation
        # and review both go through the graph, so there is one place a model can be called from.
        self.graph = ActivityGraph()           # the generate -> validate -> reprompt loop

    # ── band scope ────────────────────────────────────────────────────────
    @staticmethod
    def band_scope(profile: dict | None) -> str | None:
        """The band LETTER a learner may be grounded in, or None if they have no usable one.

        Read off the LEARNER, never off the request. A caller-supplied band could otherwise
        ground a Band C learner in Band A material, which is the exact failure this scoping
        exists to prevent, so `params['band']` is not consulted here at all.
        """
        group = (profile or {}).get("band_group")
        if not group or group == UNBANDED:
            return None
        return str(group)

    # ── profile ───────────────────────────────────────────────────────────
    def load_profile(self, learner_id: str) -> dict | None:
        """The learner row — which IS the profile now that it carries the four marks.

        One lookup, where this used to try a profile id and then fall back to a learner id.
        There is no separate profile row to resolve against any more.
        """
        return self.learners.find_by_id(learner_id)

    def build_query(self, profile: dict | None, params: dict) -> str:
        """Turn a learner's marks into the retrieval query: target what they have not mastered.

        RANKED ON A NORMALISED 0-10 SCORE, NOT THE PERCENTILE. The two answer different questions
        and only one of them is about teaching. A percentile is norm-referenced — "how far behind
        your band peers are you?" — so if a whole band is weak at phonics, every learner in it
        still ranks mid-pack and the weakness is invisible. `normalised_score` is criterion-
        referenced: how much of the rubric this learner has actually mastered. That is the thing
        an intervention should aim at. (The percentile is still the right figure for the radar
        chart and the deficiency alerts, and is untouched there.)

        A THRESHOLD, NOT A FIXED COUNT. Taking the lowest two always named a second skill even
        when the learner was solid at it, and hid a third when three were weak. Everything under
        WEAK_THRESHOLD is named instead, weakest first — one skill, or three.

        A metric with no MARK is skipped rather than treated as zero: unassessed is not weak, and
        steering a whole activity at a paper the learner never sat (writing, for all of band A)
        would be worse than a thin query. Note the guard is on the mark, not the percentile, so a
        learner whose ingest predates the percentile columns is now scored rather than skipped.

        Any `notes` from the caller are appended as a steer rather than replacing the profile.
        """
        parts: list[str] = []

        scored = [
            (key, score) for key in PLOT_FEATURES
            if (score := normalised_score(key, (profile or {}).get(key))) is not None
        ]
        if scored:
            scored.sort(key=lambda kv: kv[1])
            weak = [kv for kv in scored if kv[1] < WEAK_THRESHOLD]
            # Nobody under the threshold still gets an activity, aimed at their relative weak
            # spot. Naming nothing would leave an empty query, which the gate reads as "no marks"
            # and refuses — the wrong answer for a learner who is simply doing well.
            targets = weak or scored[:1]
            named = [f"{FEATURE_LABELS[key].lower()} {score:.1f}/10" for key, score in targets]
            parts.append("literacy activity targeting " + " and ".join(named))

        for extra in (params.get("literacy_objective"), params.get("notes")):
            if extra:
                parts.append(extra)

        # No marks and no steer: deliberately left thin so the similarity gate below refuses
        # rather than the LLM inventing from a generic query. LearnerDetailPage reads this empty
        # string as "this learner has no scores yet", so it must stay empty, not become a stub.
        return " — ".join(parts)

    # ── generation ────────────────────────────────────────────────────────
    def generate(self, learner_id: str, params: dict) -> dict:
        profile = self.load_profile(learner_id)
        query = self.build_query(profile, params)

        # Guardrail 0 — no band, no grounding. Refused BEFORE the embedder and the RPC, because
        # an unscoped retrieval is precisely the thing that must not happen: it would hand this
        # learner another band's curriculum.
        band_group = self.band_scope(profile)
        if band_group is None:
            return self._refusal(learner_id, query, [], None, reason=(
                "This learner has no band on record, and an activity can only be grounded in "
                "their own band's curriculum. Set their band before generating."
            ))

        chunks = self.curriculum.retrieve(
            query,
            band_group=band_group,           # the learner's band letter — never the caller's
            concept=params.get("concept"),
            stage=params.get("stage"),
            k=params.get("k") or 3,
        )

        # Guardrail 1 — refuse before spending an LLM call when grounding is thin.
        best = top_similarity(chunks)
        if not chunks or best is None or best < MIN_SIMILARITY:
            return self._refusal(learner_id, query, chunks, best, band_group=band_group)

        # The band the model is told is the band actually retrieved from, not whatever the caller
        # asked for — otherwise the prompt could name a band the grounding does not come from.
        echoed = {**self._request_params(params), "band": band_group}
        prompt = build_activity_prompt(chunks, echoed, profile)

        # The generate -> validate -> reprompt loop (UC3 steps 6, 6a, 6b). Replaces a bare
        # llm.complete(): the draft is now reviewed against the DAS framework and the same
        # grounding it was built from, and is reprompted with the reviewer's notes until it
        # passes or the retries run out.
        result = self.graph.run(prompt, system=SYSTEM_PROMPT, chunks=chunks,
                                params=echoed, profile=profile)
        text = result["content"]

        # Guardrail 2 — the model can still self-refuse past the similarity gate
        # (an off-topic request whose generic tokens sneak over the threshold). The graph
        # short-circuits on this rather than spending retries reviewing a refusal.
        if result["refused"] or model_refused(text):
            return self._refusal(learner_id, query, chunks, best,
                                 band_group=band_group, model_text=text)

        grounding = [self._chunk_summary(c) for c in chunks]
        activity = {
            "learner_id": profile["id"] if profile else None,
            # `grounding` is STORED, not just returned. A therapist opening this learner months
            # later — or a colleague who never ran the generation — must still be able to see
            # which curriculum pages the activity came from. `grounded_on` cannot carry that: it
            # is a text[] of compact labels, with no concept, stage or similarity. Rows written
            # before this existed have no `grounding` key, and the UI falls back to `grounded_on`.
            "content": {"text": text, "query": query, "grounding": grounding},
            "literacy_objective": params.get("literacy_objective", ""),
            "level": params.get("level") or params.get("band") or "",
            # VALIDATED or FLAGGED — the reviewer's verdict, not a placeholder. `retry_count`
            # rides along so "validated on the third attempt" stays answerable from the row.
            "status": result["status"],
            "retry_count": result["retry_count"],
            # Kept alongside the richer copy above: the shared PDF renders it (pdf_renderer).
            "grounded_on": [self._chunk_label(c) for c in chunks],
        }
        self.activities.save(activity)

        return {
            "status": result["status"],
            "content": text,
            "query": query,
            "grounding": grounding,
            "learner_id": profile["id"] if profile else None,
            "retry_count": result["retry_count"],
            # Why it was flagged. The page shows this next to a FLAGGED activity so the therapist
            # knows what the reviewer objected to instead of guessing; empty when it validated.
            "review_notes": result["notes"] if result["status"] == "FLAGGED" else "",
        }

    def list_activities(self, learner_id: str) -> list[dict]:
        return self.activities.find_by_learner(learner_id)

    # ── helpers ───────────────────────────────────────────────────────────
    def _request_params(self, params: dict) -> dict:
        """The filters/notes the prompt should echo back — retrieval knobs like `k`
        are ours, not the model's business."""
        keys = ("band", "concept", "stage", "level", "literacy_objective", "notes")
        return {k: params[k] for k in keys if params.get(k)}

    def _refusal(self, learner_id, query, chunks, best,
                 band_group=None, model_text=None, reason=None) -> dict:
        """INSUFFICIENT_CONTEXT response. Not persisted — a refusal is not an activity.

        The reason has to distinguish three genuinely different situations, because "not enough
        grounding" sends a therapist looking for the wrong problem: the band has no corpus at
        all, the corpus exists but nothing matched well enough, or the model itself declined.
        """
        if reason is not None:
            pass                                    # caller supplied a specific one
        elif model_text is not None:
            reason = "The model judged the retrieved curriculum insufficient for this request."
        elif not chunks and band_group and self._band_is_empty(band_group):
            reason = (
                f"No Band {band_group} curriculum has been ingested, so there is nothing to "
                f"ground a Band {band_group} activity in. Activities are never built from "
                f"another band's material."
            )
        else:
            score = f"{best:.3f}" if isinstance(best, (int, float)) else "none"
            scope = f" within Band {band_group}" if band_group else ""
            reason = (
                f"Retrieved {len(chunks)} curriculum chunk(s){scope}; best similarity {score} "
                f"is below the {MIN_SIMILARITY} gate. Loosen the filters or ingest more "
                f"curriculum for this profile's needs."
            )
        return {
            "status": INSUFFICIENT_CONTEXT,
            "content": (model_text or "").strip(),
            "reason": reason,
            "query": query,
            "grounding": [self._chunk_summary(c) for c in chunks],
            "learner_id": learner_id,
        }

    def _band_is_empty(self, band_group: str) -> bool:
        """True if no chunk exists for this band at all. Refusal path only — never on the happy
        path — and it must not turn a refusal into a 500, so a failed count answers 'not empty'
        and the caller falls back to the generic similarity wording."""
        try:
            return self.chunks.count_by_band_group(band_group) == 0
        except Exception:
            return False

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
