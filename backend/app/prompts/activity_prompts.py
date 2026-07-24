"""Prompt + guardrail layer for curriculum-grounded activity generation.

The generator is a RAG node: it must build a learning activity ONLY from the curriculum chunks
retrieved for the request, and refuse (INSUFFICIENT_CONTEXT) rather than invent when the grounding
is thin. `SYSTEM_PROMPT` is passed to LLMApiClient.complete(system=...) as the system role;
`build_activity_prompt` produces the user message (grounding block + request). `MIN_SIMILARITY`
is the retrieval gate the caller uses to short-circuit before ever reaching the LLM.
"""
from __future__ import annotations

INSUFFICIENT_CONTEXT = "INSUFFICIENT_CONTEXT"  # sentinel the model must emit when grounding is thin
MIN_SIMILARITY = 0.50  # top-chunk cosine similarity below this => refuse without calling the LLM.
# Tuned to nomic-embed-text's narrow score band: out-of-domain queries land ~0.42, real matches
# 0.58+. 0.50 sits in the gap so junk is refused and genuine requests pass.

SYSTEM_PROMPT = f"""You are a curriculum designer for the DAS D.I.A.L literacy programme.

Design ONE learning activity for the requested learner, using ONLY the grounding activities
provided in the user message. Follow these rules strictly:

- Ground every step, material, and example in the provided activities. Do NOT introduce steps,
  materials, vocabulary, or facts that are not supported by them.
- Adapt and sequence the grounding content for the request (band, concept, stage, any notes);
  you may rephrase for the learner, but do not invent new pedagogy.
- If the grounding activities do NOT cover the request, reply with exactly `{INSUFFICIENT_CONTEXT}`
  on the first line, followed by a short bulleted list of what is missing. Never fabricate an
  activity to fill the gap.

Output a clear, teacher-ready activity: a title, objective, materials, and numbered steps.
"""


def _fmt_chunk(i: int, chunk: dict) -> str:
    """One retrieved chunk rendered as readable grounding text (never a raw dict dump)."""
    title = chunk.get("activity_title") or "(untitled)"
    concept = chunk.get("concept") or "-"
    stage = chunk.get("stage") or "-"
    src = chunk.get("source_file") or "?"
    page = chunk.get("page_start") or "?"
    parts = [
        f"[{i}] {title}  (concept: {concept} | stage: {stage} | source: {src} p.{page})",
        (chunk.get("content_md") or "").strip(),
    ]
    if chunk.get("answer_key"):
        parts.append("Answer key:\n" + chunk["answer_key"].strip())
    return "\n".join(parts)


def format_context(chunks: list[dict]) -> str:
    """Render retrieved chunks into a grounding block. Full content_md — never truncated."""
    if not chunks:
        return "(no grounding activities were retrieved)"
    return "\n\n---\n\n".join(_fmt_chunk(i, c) for i, c in enumerate(chunks, 1))


def _fmt_request(params: dict, profile: dict | None) -> str:
    """The request line: the filters/notes the activity should target, plus profile if given."""
    fields = {k: v for k, v in params.items() if v}
    req = ", ".join(f"{k}={v}" for k, v in fields.items()) or "(no specific filters)"
    lines = [f"Request: {req}"]
    if profile:
        lines.append(f"Learner profile: {profile}")
    return "\n".join(lines)


def build_activity_prompt(chunks: list[dict], params: dict, profile: dict | None = None) -> str:
    """The user message: grounding activities followed by the request. System role is separate."""
    return (
        "GROUNDING ACTIVITIES (use only these):\n\n"
        f"{format_context(chunks)}\n\n"
        "========\n\n"
        f"{_fmt_request(params, profile)}\n\n"
        "Design the learning activity now, following the system rules."
    )
