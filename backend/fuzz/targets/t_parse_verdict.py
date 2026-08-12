"""Target for `app/prompts/activity_prompts.py` — the reviewer-verdict parser.

WHY THIS UNIT. It is the only place in the request path that parses text an LLM wrote, which makes
it the one input the project genuinely cannot constrain: every other string arrives from our own
UI or our own database. Its docstring also states an unusually strong security property —

    FAILS CLOSED. An unreadable verdict is not a pass - it is a review that did not happen, and
    treating it as approval is exactly the bug the previous `return {"valid": True}` stub was.

— and a property stated that plainly is a property worth attacking. If a fuzzer can find an input
that makes `parse_verdict` return `valid=True`, an unreviewed activity reaches a therapist marked
as approved.

THE CRASH ORACLE HAS A SPECIFIC TARGET HERE. `parse_verdict` guards `json.loads` with
`except json.JSONDecodeError`, which is not the only thing `json.loads` raises: CPython's scanner
recurses per nesting level, so a deeply nested object raises RecursionError instead, and that is
not caught. Nothing plants such an input. The seeds are ordinary model replies and the mutators
are the generic ones in `mutators.py`; a nested payload has to be built by the repeat-span
operator amplifying a brace run, which is the whole point of mutation-based fuzzing.

The three functions here are exercised together because they sit on the same request path and a
single decoded input feeds all three: the raw reply text goes to `parse_verdict` and
`model_refused`, and its numeric tokens become the retrieved-chunk similarities `top_similarity`
ranks.
"""
from __future__ import annotations

import json

from app.prompts.activity_prompts import model_refused, parse_verdict, top_similarity
from fuzz.oracles import invariant
from fuzz.targets.base import Target, as_text, register

#: Real reply shapes: the bare object, the fenced object models actually emit, prose either side,
#: the refusal sentinel, and the malformed cases the parser is documented to survive.
SEED_REPLIES = [
    b'{"valid": true, "notes": "Grounded in the retrieved activities."}',
    b'{"valid": false, "notes": "Introduces a phoneme not present in the context."}',
    b'```json\n{"valid": true, "notes": "ok"}\n```',
    b'Here is my verdict:\n\n{"valid": false, "notes": "off band"}\n\nHope that helps.',
    b"INSUFFICIENT_CONTEXT",
    b"**Insufficient Context** - I cannot review this without the source material.",
    b'{"valid": "yes", "notes": "wrong type"}',
    b'{"notes": "no verdict key at all"}',
    b"{}",
    b"",
]

#: A JSON-ish grammar, so the generation-based strategy produces well-formed objects that reach
#: past the `find("{")` guard instead of being rejected at the door. Recursion through <value> is
#: what lets it nest; `grammar.py` bounds the depth so a single generation cannot run away.
VERDICT_GRAMMAR = {
    "<start>": ["<fenced>", "<object>", "<prose><object><prose>"],
    "<fenced>": ["```json\n<object>\n```"],
    "<object>": ["{<pairs>}", "{}"],
    "<pairs>": ["<pair>", "<pair>, <pairs>"],
    "<pair>": ['"valid": <value>', '"notes": <value>', '"<word>": <value>'],
    "<value>": ["true", "false", "null", "<number>", '"<word>"', "<object>", "[<value>]"],
    "<number>": ["0", "1", "-1", "0.5", "1e999", "NaN"],
    "<word>": ["ok", "valid", "notes", "insufficient_context", ""],
    "<prose>": ["Here is my verdict: ", "\n\nHope that helps.", ""],
}


@register
class ParseVerdictTarget(Target):
    name = "parse_verdict"
    #: All three functions are documented as total over `str | None`. Nothing is allowed to
    #: escape, so an empty `allowed` tuple means ANY exception is a finding.
    allowed = ()
    oracles = ("crash", "hang", "invariant")
    max_size = 16384
    measured = "app.prompts"
    grammar = VERDICT_GRAMMAR

    def seeds(self) -> list[bytes]:
        return list(SEED_REPLIES)

    def run(self, data: bytes) -> None:
        raw = as_text(data)

        verdict = parse_verdict(raw)

        # The declared return shape.
        invariant(isinstance(verdict, dict), f"parse_verdict returned {type(verdict).__name__}")
        invariant(
            isinstance(verdict.get("valid"), bool),
            f"parse_verdict returned a non-bool valid: {verdict.get('valid')!r}",
        )
        invariant(
            isinstance(verdict.get("notes"), str),
            f"parse_verdict returned a non-str notes: {verdict.get('notes')!r}",
        )

        # FAILS CLOSED, checked by a necessary condition rather than by reimplementing the parser.
        # An approval it did not read out of the text is an approval it invented; the weakest
        # honest test of that is that the token has to appear somewhere in the input at all.
        # Deliberately not a reimplementation of the parse: a second copy of the same logic would
        # agree with the first one's bugs.
        if verdict["valid"] is True:
            invariant(
                "true" in raw.lower(),
                f"parse_verdict approved a draft from a reply containing no 'true': {raw[:120]!r}",
            )

        # Stability: re-reading the same reply must reach the same verdict. A parser whose answer
        # depends on dict ordering or on a mutable default would break here.
        invariant(
            parse_verdict(raw) == verdict,
            "parse_verdict is not deterministic on a repeated call",
        )

        refused = model_refused(raw)
        invariant(isinstance(refused, bool), f"model_refused returned {type(refused).__name__}")

        # A refusal is a claim about the FIRST LINE ONLY, per the docstring. That is testable
        # without restating the matching rule: whatever follows the first line cannot change the
        # answer. The first version of this oracle asserted "insufficient" appeared in the raw
        # first line and was simply wrong - the function strips punctuation on purpose, so it
        # (correctly) fires on 'INSUFFICI-ENT_CONTEXT', and the oracle reported the code for
        # doing exactly what its docstring promises.
        if raw.strip():
            first = raw.strip().splitlines()[0]
            invariant(
                model_refused(first) == refused,
                f"model_refused disagreed with itself on the first line alone: {first[:80]!r}",
            )

        # top_similarity over chunks built from whatever numbers the input happens to contain,
        # plus the raw text itself as a non-numeric value, which is the shape hybrid retrieval
        # produces for keyword-only rows.
        chunks = _as_chunks(raw)
        best = top_similarity(chunks)
        invariant(
            best is None or isinstance(best, (int, float)),
            f"top_similarity returned {best!r}",
        )
        # `isinstance(True, (int, float))` is True in Python, so a chunk whose similarity is a
        # bool passes the filter inside top_similarity and can be returned as the "best" score.
        # A threshold gate comparing that against MIN_SIMILARITY is comparing against 1.0.
        invariant(
            not isinstance(best, bool),
            f"top_similarity returned the bool {best!r} where a float was promised",
        )
        if best is not None:
            # NaN gets its own oracle rather than being folded into the maximum check below,
            # where `nan != nan` would report a real defect under a misleading message. A NaN
            # similarity is worth reporting on its own terms: every comparison against it is
            # False, so `best >= MIN_SIMILARITY` silently fails the retrieval gate closed, and
            # `json` parses the bare token `NaN` without complaint.
            invariant(
                best == best,  # noqa: PLR0124 - the NaN test
                "top_similarity returned NaN, which defeats every threshold comparison",
            )
            numeric = [
                c["similarity"] for c in chunks
                if isinstance(c.get("similarity"), (int, float))
            ]
            invariant(
                best == max(numeric),
                f"top_similarity returned {best!r}, not the maximum {max(numeric)!r}",
            )


def _as_chunks(raw: str) -> list[dict]:
    """Turn the input into the `list[dict]` shape retrieval hands to `top_similarity`.

    Every token that parses as a JSON scalar becomes one chunk's `similarity`, so numbers, `true`,
    `null` and quoted strings all reach the function the way a malformed retrieval row would.
    """
    chunks: list[dict] = []
    for token in raw.replace(",", " ").split()[:64]:
        try:
            value = json.loads(token)
        except Exception:  # noqa: BLE001 - a token that is not JSON is simply not a similarity
            value = None
        chunks.append({"similarity": value, "content": token})
    chunks.append({"content": raw[:200]})  # a keyword-only row: no similarity key at all
    return chunks
