"""ActivityGraph - Subsystem 3 core: the LangGraph generate -> validate loop (UC3 steps 6, 6a, 6b).

    START -> generate -> (refused?) -> END
                      -> validate -> (valid or out of retries?) -> END
                                  -> generate   [with the reviewer's notes appended]

This is the loop the UC3 sequence diagram draws. Three things it does that the previous
hand-rolled version did not, each of them the difference between a loop and a ritual:

  * THE FEEDBACK IS FED BACK. A retry that re-sends the identical prompt is a coin flip — the
    model has no idea what was wrong. `generate` appends the reviewer's notes, which is what
    alternative flow 6a ("System reprompts the Generative Agent with feedback") actually means.
  * `retry_count` IS STATE, not a loop variable. It is returned to the caller and persisted, so
    "validated on the third attempt" is answerable months later from the row alone.
  * `best_attempt` SURVIVES. Flow 6b surfaces the best attempt when retries run out; with the old
    code the last draft was overwritten and there was nothing left to surface.

A self-refusal short-circuits: if the model emits INSUFFICIENT_CONTEXT the draft is not a bad
activity, it is the model correctly declining, and sending it to review would waste every retry
rejecting something nobody asked to be written.
"""
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents.agents import GenerativeAgent, ValidativeAgent
from app.gateways.llm_client import LLMApiClient
from app.prompts.activity_prompts import model_refused

# How the reviewer's notes are handed back to the writer on a retry.
RETRY_INSTRUCTION = (
    "\n\n========\n\n"
    "YOUR PREVIOUS ATTEMPT WAS REJECTED BY THE REVIEWER.\n\n"
    "Reviewer's notes:\n{notes}\n\n"
    "Write the activity again, fixing exactly what the notes describe. Keep everything the notes "
    "did not object to, and stay inside the grounding activities above."
)


class ActivityState(TypedDict, total=False):
    """What flows between the nodes. `total=False` so a node returns only what it changed."""
    prompt: str            # the base user message (grounding + request), never mutated
    system: str            # the generator's system prompt
    chunks: list[dict]     # grounding — the reviewer needs it too, to judge criterion 1
    params: dict
    profile: dict | None

    content: str           # the current draft
    valid: bool
    notes: str             # the reviewer's feedback on the current draft
    retry_count: int       # regenerations so far; 0 means validated on the first attempt
    max_retries: int
    best_attempt: str      # the last draft produced, kept for the FLAGGED path
    refused: bool          # the model self-refused (INSUFFICIENT_CONTEXT), not a rejection


class ActivityGraph:
    """Runs the loop. One instance per service; `invoke` is per-request and holds no state."""

    def __init__(self, max_retries: int = 2, llm: LLMApiClient | None = None):
        self.max_retries = max_retries
        llm = llm or LLMApiClient()
        self.generator = GenerativeAgent(llm)
        self.validator = ValidativeAgent(llm)
        self._graph = self._build()

    # ── nodes ─────────────────────────────────────────────────────────────
    def _generate(self, state: ActivityState) -> dict:
        """Write a draft. On a retry, append the reviewer's notes and count the attempt."""
        prompt = state["prompt"]
        retry_count = state.get("retry_count", 0)

        if state.get("content"):                    # this is a retry, not the first attempt
            retry_count += 1
            notes = state.get("notes") or "(the reviewer gave no specific reason)"
            prompt = prompt + RETRY_INSTRUCTION.format(notes=notes)

        draft = self.generator.generate(prompt, system=state.get("system"))
        content = draft["content"]
        return {
            "content": content,
            "best_attempt": content,                # newest draft = most feedback applied
            "retry_count": retry_count,
            "refused": model_refused(content),
        }

    def _validate(self, state: ActivityState) -> dict:
        verdict = self.validator.validate(
            {"content": state["content"]},
            state.get("chunks") or [],
            state.get("params") or {},
            state.get("profile"),
        )
        return {"valid": verdict["valid"], "notes": verdict.get("notes", "")}

    # ── edges ─────────────────────────────────────────────────────────────
    @staticmethod
    def _after_generate(state: ActivityState) -> str:
        """A self-refusal leaves the loop immediately — it is not a draft to be reviewed."""
        return END if state.get("refused") else "validate"

    @staticmethod
    def _after_validate(state: ActivityState) -> str:
        if state.get("valid"):
            return END
        if state.get("retry_count", 0) >= state.get("max_retries", 0):
            return END                              # out of attempts -> the caller FLAGs it
        return "generate"

    def _build(self):
        builder = StateGraph(ActivityState)
        builder.add_node("generate", self._generate)
        builder.add_node("validate", self._validate)
        builder.add_edge(START, "generate")
        builder.add_conditional_edges("generate", self._after_generate,
                                      {"validate": "validate", END: END})
        builder.add_conditional_edges("validate", self._after_validate,
                                      {"generate": "generate", END: END})
        return builder.compile()

    # ── entry point ───────────────────────────────────────────────────────
    def run(self, prompt: str, *, system: str | None = None, chunks: list[dict] | None = None,
            params: dict | None = None, profile: dict | None = None) -> dict:
        """Generate and validate, returning the final state as a plain dict.

        `status` is the caller's answer to "may a therapist use this as-is?":

            VALIDATED   the reviewer passed it (on attempt `retry_count` + 1)
            FLAGGED     retries ran out with it still rejected — usable, but needs a human
            GENERATED   the model self-refused; the SERVICE turns this into INSUFFICIENT_CONTEXT
                        and persists nothing, so it is never stored with this status

        `GenerationFailedError` from the writer is deliberately NOT caught: a dead LLM edge is
        infrastructure, not a bad activity, and must not be recorded as a flagged draft.
        """
        final = self._graph.invoke({
            "prompt": prompt,
            "system": system or "",
            "chunks": chunks or [],
            "params": params or {},
            "profile": profile,
            "retry_count": 0,
            "max_retries": self.max_retries,
            "valid": False,
            "notes": "",
            "refused": False,
        })

        if final.get("refused"):
            status = "GENERATED"
        elif final.get("valid"):
            status = "VALIDATED"
        else:
            status = "FLAGGED"

        return {
            "content": final.get("content", ""),
            "status": status,
            "retry_count": final.get("retry_count", 0),
            "notes": final.get("notes", ""),
            "best_attempt": final.get("best_attempt", ""),
            "refused": bool(final.get("refused")),
        }
