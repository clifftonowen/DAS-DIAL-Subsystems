"""Prompt + guardrail layer for curriculum-grounded activity generation.

The generator is a RAG node: it must build a learning activity ONLY from the curriculum chunks
retrieved for the request, and refuse (INSUFFICIENT_CONTEXT) rather than invent when the grounding
is thin. `SYSTEM_PROMPT` is passed to LLMApiClient.complete(system=...) as the system role;
`build_activity_prompt` produces the user message (grounding block + request). `MIN_SIMILARITY`
is the retrieval gate the caller uses to short-circuit before ever reaching the LLM.
"""
from __future__ import annotations

from app.ingestion.dial_features import (
    FEATURE_LABELS, FEATURE_MAXIMA, PLOT_FEATURES, normalised_score,
)

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


def _fmt_mark(profile: dict, key: str) -> str | None:
    """One DIAL metric as 'Phonics 31/46 = 6.2/10 (58 pct)', or None if never assessed.

    All three figures earn their place, and they are not substitutes:

      31/46      the mark actually awarded, against the rubric a therapist knows
      6.2/10     the normalised score — the ONLY one comparable across the four, since phonics
                 is out of 46 and word reading out of 10, and the one build_query ranked on to
                 choose what this activity targets. Stating it keeps the prompt and the query
                 telling the model the same story.
      58 pct     where that sits among the learner's band peers, which neither of the others say

    KEYED ON THE MARK, not the percentile, matching build_query — a learner whose ingest predates
    the percentile columns has a real mark and should be described, not silently dropped.
    """
    raw = profile.get(key)
    score = normalised_score(key, raw)
    if score is None:
        return None  # not assessed. Say nothing: absent is not the same as weak.
    out = f"{FEATURE_LABELS[key]} {raw:g}/{FEATURE_MAXIMA[key]:g} = {score:.1f}/10"
    pct = profile.get(f"{key}_pct")
    return f"{out} ({pct:g} pct)" if isinstance(pct, (int, float)) else out


def _fmt_profile(profile: dict) -> str:
    """The learner's four DIAL marks, and nothing else. Empty string if none were assessed.

    A WHITELIST, deliberately, not a blacklist. `learners` carries 26 columns — pseudonym,
    student_id, tier, age, school_level, cluster labels, timestamps — and completions go to a
    hosted model, so everything interpolated here leaves the machine. Naming what may leave is
    the only version of this that stays correct when someone adds a column to the table.

    Band group rides along because it is the rubric the raw marks should be read against, and
    the percentiles are ranked within it.
    """
    marks = [m for m in (_fmt_mark(profile, key) for key in PLOT_FEATURES) if m]
    if not marks:
        return ""
    band = profile.get("band_group")
    head = f"Learner marks (band {band})" if band else "Learner marks"
    return f"{head}: " + "; ".join(marks)


def _fmt_request(params: dict, profile: dict | None) -> str:
    """The request line: the filters/notes the activity should target, plus marks if given."""
    fields = {k: v for k, v in params.items() if v}
    req = ", ".join(f"{k}={v}" for k, v in fields.items()) or "(no specific filters)"
    lines = [f"Request: {req}"]
    if profile:
        summary = _fmt_profile(profile)
        if summary:  # a learner with no marks at all adds no line, not an empty header
            lines.append(summary)
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


def model_refused(text: str | None) -> bool:
    """True if the model self-refused with an INSUFFICIENT_CONTEXT signal on its first line.

    Tolerant of spacing/case/punctuation — models write 'INSUFFICIENT CONTEXT', bold it, or
    lowercase it, and almost never emit the exact underscore sentinel. Shared by the API
    service and the scripts.generate_activity CLI so both refuse on the same rule.
    """
    if not text or not text.strip():
        return False
    first_line = text.strip().splitlines()[0]
    norm = "".join(ch for ch in first_line.lower() if ch.isalnum())  # drop spaces/_/markdown
    return norm.startswith("insufficientcontext")


def top_similarity(chunks: list[dict]) -> float | None:
    """Best semantic similarity across retrieved chunks, or None if none carry one.

    Hybrid retrieval orders by RRF score, so the first row is not necessarily the most
    semantically similar, and keyword-only rows have similarity None — hence max(), not [0].
    """
    sims = [c["similarity"] for c in chunks if isinstance(c.get("similarity"), (int, float))]
    return max(sims) if sims else None
