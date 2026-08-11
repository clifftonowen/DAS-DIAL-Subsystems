"""GenerativeAgent + ValidativeAgent - the two LLM nodes in the graph.

Both are STATELESS: one call in, one verdict out, no retry logic and no knowledge of how many
attempts have been made. The loop that drives them lives in ActivityGraph, so that the retry
policy can be tested without a model and each agent can be tested without a loop.
"""
from app.gateways.llm_client import LLMApiClient
from app.prompts.activity_prompts import (
    VALIDATION_SYSTEM_PROMPT, build_validation_prompt, parse_verdict,
)


class GenerationFailedError(Exception):
    """The model could not be reached, or returned nothing usable.

    Raised rather than returned so it cannot be mistaken for a draft. An empty completion that
    flowed on as `content` would be validated (and rejected) as if the model had written a bad
    activity, which sends a therapist looking for a prompt problem when the real fault is the LLM
    edge being down.
    """


class GenerativeAgent:
    """Writes a draft activity from a prompt."""

    def __init__(self, llm: LLMApiClient):
        self.llm = llm

    def generate(self, prompt: str, system: str | None = None) -> dict:
        try:
            raw = self.llm.complete(prompt, system=system)
        except Exception as exc:                       # timeout, HTTP error, bad key…
            raise GenerationFailedError(str(exc)) from exc
        if not raw or not raw.strip():
            raise GenerationFailedError("The model returned an empty completion.")
        return {"content": raw, "status": "GENERATED"}


class ValidativeAgent:
    """Judges a draft against the DAS review framework and the grounding it was built from.

    Replaces a stub that returned `{"valid": True}` unconditionally — which made the whole
    generate/validate loop a no-op, since nothing could ever be rejected or flagged.
    """

    def __init__(self, llm: LLMApiClient):
        self.llm = llm

    def validate(self, activity: dict, chunks: list[dict], params: dict,
                 profile: dict | None = None) -> dict:
        """`{"valid": bool, "notes": str}` — notes is the feedback for the next attempt.

        A reviewer that cannot be reached FAILS CLOSED, exactly as an unreadable verdict does
        (see `parse_verdict`): an activity nobody reviewed must not be recorded as validated. The
        loop treats that as a rejection, so a persistently unreachable reviewer ends with the
        activity FLAGGED for a therapist rather than silently approved.
        """
        content = (activity or {}).get("content") or ""
        if not content.strip():
            return {"valid": False, "notes": "There was no draft activity to review."}

        prompt = build_validation_prompt(content, chunks, params, profile)
        try:
            raw = self.llm.complete(prompt, system=VALIDATION_SYSTEM_PROMPT)
        except Exception as exc:
            return {"valid": False, "notes": f"The reviewer could not be reached: {exc}"}
        return parse_verdict(raw)
