"""Target for the HTTP surface — the whole FastAPI app behind an in-process client.

WHAT THIS ORACLE IS. Every other target checks a function against its docstring. This one checks
the API against a rule the framework itself defines: a request is either serviced or refused with
a 4xx, and a 5xx means the server broke on input it should have rejected at the boundary. Pydantic
is supposed to make that unreachable. Where it does not, the gap is a validation gap, and that is
the "security" property the brief asks the delivered software to be tested for.

WHY IN-PROCESS AND NOT OVER A SOCKET. `TestClient` runs the real app in this process with
`raise_server_exceptions` left at its default, so an unhandled exception propagates out of the
call and the engine's CRASH oracle records the real application traceback. Over a socket the same
defect arrives as an opaque `500` with the stack trace in a log we are not reading. The traceback
is the finding; a status code is just the symptom.

THE THREE SEAMS, AND WHY THEY ARE NOT OPTIONAL. The app talks to Supabase and to an LLM. A
campaign issues millions of requests, so:

  auth       `dependency_overrides[current_therapist]`, mirroring the `auth_ok` fixture. Without
             it every request is a 401 and the fuzzer tests the bearer parser and nothing else.
  database   FakeSupabase, installed over all five binding sites. Rebuilt PER INPUT, because the
             fake accumulates inserted rows and a query log forever; an eight-hour run against one
             instance is an unbounded memory leak, and state surviving between inputs would make
             a finding depend on everything the fuzzer happened to send before it.
  LLM        `LLMApiClient.use_provider`. An overnight loop against real Gemini or Ollama is a
             billing incident, is rate-limited into uselessness, and makes every finding
             unreproducible because the model's reply is different next time.
  email      `EmailGateway.send`, neutered to a counter.

THE EMAIL SEAM IS HERE BECAUSE IT WAS MISSED ONCE. The first smoke run of this target relayed four
real messages through Gmail before anyone noticed: `.env` has `EMAIL_ENABLED=True` and a live
`SMTP_HOST`, so `POST /share` took the delivery branch, and the fuzzer had generated recipient
addresses by mutating `therapist@example.com` into things like `tist@eherapxample.com`. Thirty
seconds sent four. Eight hours would have sent tens of thousands, from the project's own account.

The general rule that follows, and the reason this docstring is long: BEFORE FUZZING AN ENDPOINT,
ENUMERATE WHAT IT CAN TOUCH OUTSIDE THIS PROCESS. Stubbing the two obvious boundaries is not the
same as stubbing all of them, and the one that gets missed is the one nobody thinks of as a
boundary. `_assert_hermetic()` below turns that from a thing we remembered into a thing that is
checked at import.

WHAT IS DELIBERATELY NOT FUZZED HERE.

  `/dashboard/*`   four bare `except Exception: pass` handlers returning hardcoded demo data
                   (routers/dashboard.py:26,39,55,71). They cannot fail, so a campaign against
                   them proves nothing about the system and only dilutes the budget. The swallow
                   is itself worth reporting, but a fuzzer is not how you find it.
  `/auth/*`        `Credentials.email` is an `EmailStr`, so essentially everything generated is
                   refused at the boundary with a 422. The interesting half of signup and login
                   lives in Supabase's own auth service, which is exactly the thing the fake
                   replaces, so a finding here would be a finding about our fake.
"""
from __future__ import annotations

import json
from urllib.parse import quote

from fastapi.testclient import TestClient

from app.core.security import current_therapist
from app.gateways.llm_client import LLMApiClient
from app.main import app
from fuzz.oracles import invariant
from fuzz.targets.base import Target, as_text, register

LEARNER_ID = "11111111-1111-4111-8111-111111111111"
ACTIVITY_ID = "22222222-2222-4222-8222-222222222222"


# --------------------------------------------------------------------------- #
# The seams
# --------------------------------------------------------------------------- #
class _FakeLLM:
    """The embedder, the writer and the reviewer, all canned.

    Dispatches nothing on `system`: unlike the integration suite's fake this one does not care
    which agent is calling, it only has to return promptly and never touch the network. The
    verdict it returns is a valid one so the generation path runs to completion rather than
    short-circuiting into the refusal branch on every single request.
    """

    embed_dim = 3
    embedding_model = "fake-embed"

    def embed(self, text, is_query=False):
        return [0.1, 0.2, 0.3]

    def embed_many(self, texts, is_query=False):
        return [[0.1, 0.2, 0.3] for _ in texts]

    def complete(self, prompt, system=None, temperature=None, seed=None):
        if system is not None and "verdict" in str(system).lower():
            return '{"valid": true, "notes": "ok"}'
        return "Rhyme Time\n\n1. Clap the onset.\n2. Blend the rime."


def _seed_rows() -> dict:
    """The minimum database for a request to reach real code rather than bounce off a 404."""
    return {
        "learners": [{
            "id": LEARNER_ID, "pseudonym": "Fuzz Learner", "tier": "Tier 2",
            "band": "A2", "band_group": "A",
            "phonics": 12.0, "word_reading_accuracy": 7.0,
            "word_spelling": 4.0, "writing": None,
        }],
        "learning_activities": [{
            "id": ACTIVITY_ID, "learner_id": LEARNER_ID,
            "content": {"text": "A generated activity."},
            "literacy_objective": "onset and rime", "level": "A2",
            "status": "GENERATED", "grounded_on": [],
        }],
        "curriculum_chunks": [{
            "id": "c1", "band": "A1", "concept": "action_predicate", "stage": "practice",
            "similarity": 0.70, "doc_type": "lesson_plan",
            "activity_title": "Chunk c1", "content_md": "Clap the onset, then blend the rime.",
            "source_file": "2) A1.pdf", "page_start": "14", "answer_key": None,
        }],
        "learner_sittings": [],
        "reviews": [],
    }


#: Holds the current fake so the patched getters resolve it at call time rather than closing over
#: whichever instance existed when the seam was installed.
_STATE: dict = {"fake": None}


def _install_seams() -> None:
    """Patch auth, the database and the LLM. Runs once, at import."""
    from tests.support.fake_supabase import FakeSupabase  # noqa: F401 - imported for its side use

    import app.core.security as security
    import app.core.supabase_client as supabase_client
    import app.gateways.auth_gateway as auth_gateway
    import app.repositories.base as repositories_base

    getter = _get_fake

    # Both getters are lru_cached and may already hold a real client built from .env.
    supabase_client.get_supabase.cache_clear()
    supabase_client.get_auth_supabase.cache_clear()

    # Five binding sites, because several modules do `from ... import get_supabase` at import
    # time and therefore hold their own reference. Patching only the source module leaves those
    # pointing at the real client, which is how a "hermetic" run reaches the network.
    supabase_client.get_supabase = getter
    supabase_client.get_auth_supabase = getter
    repositories_base.get_supabase = getter
    security.get_supabase = getter
    auth_gateway.get_auth_supabase = getter

    app.dependency_overrides[current_therapist] = lambda: "test-therapist-id"
    LLMApiClient.use_provider(_FakeLLM())

    # SMTP. Patched on the CLASS, not on ShareService, because ShareService builds its own
    # EmailGateway in __init__ and a new instance is created per request - there is no single
    # object to swap. Overriding the method covers every instance that will ever exist.
    import app.gateways.email_gateway as email_gateway

    def _no_send(self, pdf_bytes: bytes, recipient_email: str) -> bool:
        _STATE["emails"] = _STATE.get("emails", 0) + 1
        return True

    email_gateway.EmailGateway.send = _no_send

    _assert_hermetic()


def _assert_hermetic() -> None:
    """Refuse to start unless every outbound boundary is stubbed.

    A campaign is unattended by design, so "we remembered to stub it" is not a control. This fails
    the import rather than the request: a target that reaches the network is not a slightly worse
    fuzzer, it is a thing that must not run at all.
    """
    from app.gateways.email_gateway import EmailGateway
    import app.core.supabase_client as supabase_client
    import app.repositories.base as repositories_base
    import app.core.security as security
    import app.gateways.auth_gateway as auth_gateway

    problems = []

    if EmailGateway.send.__name__ != "_no_send":
        problems.append("EmailGateway.send is live - it would relay real SMTP")
    if LLMApiClient._override is None:  # noqa: SLF001 - the seam is the private class attribute
        problems.append("LLMApiClient has no provider override - it would call a real model")
    for module in (supabase_client, repositories_base, security):
        if getattr(module, "get_supabase", None) is not _get_fake:
            problems.append(f"{module.__name__}.get_supabase is not the fake")
    for module in (supabase_client, auth_gateway):
        if getattr(module, "get_auth_supabase", None) is not _get_fake:
            problems.append(f"{module.__name__}.get_auth_supabase is not the fake")
    if current_therapist not in app.dependency_overrides:
        problems.append("current_therapist is not overridden - every request would be a 401")

    if problems:
        raise RuntimeError(
            "fuzz target http_api refuses to run, the process is not hermetic:\n  "
            + "\n  ".join(problems)
        )


def _get_fake():
    """The single getter installed over every Supabase binding site.

    A module-level function rather than a closure so `_assert_hermetic` can check each binding is
    literally this object; an `is` test against a fresh lambda would always fail.
    """
    return _STATE["fake"]


def _reset_database() -> None:
    from tests.support.fake_supabase import FakeSupabase

    _STATE["fake"] = FakeSupabase(seed=_seed_rows())


_install_seams()
_reset_database()
_CLIENT = TestClient(app)


# --------------------------------------------------------------------------- #
# The request table
# --------------------------------------------------------------------------- #
#: Bodies that are known-valid, so an injected field is the ONLY thing wrong with the request.
#: Fuzzing a body that is already malformed everywhere only ever reaches the 422 branch; changing
#: one field at a time is what gets past validation and into the handler.
CONFIRM_BODY = {
    "learner_id": LEARNER_ID,
    "assessment_date": "2026-03-01",
    "risk_score": 0.4,
    "task_results": {"blending": 8},
    "strengths": ["blending"],
    "weaknesses": ["segmenting"],
    "confidence_score": 0.8,
    "semester": "2026 Sem 1",
    "band": "A2",
    "band_group": "A",
    "writing_score": None,
    "phonics_score": 12.0,
    "word_reading_score": 7.0,
    "word_spelling_score": 4.0,
}

GENERATE_BODY = {
    "literacy_objective": "onset and rime",
    "level": "A2",
    "band": None,
    "concept": "action_predicate",
    "stage": "practice",
    "notes": "",
    "k": 3,
    "extra": {},
}

REVIEW_BODY = {"activity_id": ACTIVITY_ID, "text": "Looks good.", "approval_status": "APPROVED"}

SHARE_BODY = {"activity_id": ACTIVITY_ID, "recipient_email": "therapist@example.com"}

#: (method, path template, kind, template body). `{learner_id}` / `{activity_id}` are filled from
#: the fuzz input so path handling is exercised too, not just bodies.
ENDPOINTS: list[tuple[str, str, str, dict | None]] = [
    ("POST", "/assessments/confirm", "json", CONFIRM_BODY),
    ("POST", "/activities/{learner_id}/generate", "json", GENERATE_BODY),
    ("POST", "/reviews", "json", REVIEW_BODY),
    ("POST", "/share", "json", SHARE_BODY),
    ("POST", "/assessments/preview", "multipart", None),
    ("POST", "/profiles/{learner_id}", "path", None),
    ("GET", "/learners", "query", None),
    ("GET", "/learners/{learner_id}", "path", None),
    ("GET", "/learners/{learner_id}/overview", "path", None),
    ("GET", "/learners/{learner_id}/sittings", "path", None),
    ("GET", "/reviews/{activity_id}", "path", None),
    ("GET", "/assessments/semesters", "path", None),
]

#: Values worth trying in a field whose template value is an integer. The gaps these probe are
#: real: `GenerationParams.k` has no `ge`/`le`, so a negative or astronomically large `k` reaches
#: the retrieval RPC as `match_count`.
INTERESTING_INTS = [0, -1, 1, 2, 3, 2**31 - 1, -(2**31), 10**9, 10**18, 2**63]

#: Filenames for the multipart endpoint. `validate_format` checks only the extension, so the
#: interesting cases are the ones that pass that check while carrying something else entirely,
#: and the ones that probe how the check itself is spelled.
FILENAMES = [
    "report.pdf", "report.docx", "report.PDF", "report.DocX",
    "report.txt", "report", "report.pdf.txt", "report.txt.pdf",
    ".pdf", "report.pdf\x00.txt",
]

SEED_REQUESTS = [
    bytes([i, 0, 0, 0]) + json.dumps(body).encode() if body else bytes([i, 0, 0, 0]) + b"seed"
    for i, (_m, _p, _k, body) in enumerate(ENDPOINTS)
] + [
    bytes([0, 1, 7, 0]) + b"2026 Sem 1",       # the semester field of /assessments/confirm
    bytes([1, 1, 6, 0]) + b"3",                 # the k field of /generate
    bytes([3, 1, 1, 0]) + b"therapist@example.com",
    bytes([2, 1, 1, 0]) + b"Looks good.",
]


@register
class HttpApiTarget(Target):
    name = "http_api"
    #: Nothing is allowed to escape. The app is a web server: every input has a correct HTTP
    #: answer, and an exception reaching this frame is by definition an unhandled 500.
    allowed = ()
    oracles = ("crash", "hang", "invariant")
    #: Far smaller than the string targets' 32-64KB, and the reason is throughput. One request
    #: costs milliseconds where a function call costs microseconds, and `share_service.EMAIL_RE`
    #: backtracks quadratically in the length of its input - a 100KB body took 10.5 SECONDS in the
    #: first smoke run, so a handful of them consumed the entire budget and the campaign managed 4
    #: execs/s. 4KB is still an order of magnitude past any real request and keeps the worst case
    #: bounded. The quadratic regex is a genuine finding; it just should not also be a denial of
    #: service against our own fuzzer.
    max_size = 4096
    measured = "app"
    #: One request costs ~7 ms against ~6 us for a string function, so the 1000-input default
    #: makes a generation take eight seconds and the attribution pass that follows a winning one
    #: take up to a minute. Measured: the guided run managed 17 execs/s against mutation's 124.
    #: 150 keeps a generation near a second and attribution bounded.
    suite_size = 150

    def seeds(self) -> list[bytes]:
        return list(SEED_REQUESTS)

    def run(self, data: bytes) -> None:
        header = data[:4].ljust(4, b"\x00")
        payload = data[4:]

        method, template, kind, body = ENDPOINTS[header[0] % len(ENDPOINTS)]
        text = as_text(payload)

        # Each input starts from the same database. See the module note: without this the fake
        # grows without bound and findings stop being reproducible in isolation.
        _reset_database()

        path = template.replace("{learner_id}", _path_value(header[2], text, LEARNER_ID))
        path = path.replace("{activity_id}", _path_value(header[2], text, ACTIVITY_ID))

        response = _send(method, path, kind, body, header, text, payload)

        # THE PRIMARY ORACLE. 4xx is the app doing its job; 5xx is the app breaking on input it
        # was supposed to refuse. Unhandled exceptions never reach here at all - they propagate
        # out of _send into the engine's crash oracle, with the traceback attached.
        invariant(
            response.status_code < 500,
            f"{method} {path} returned {response.status_code} for {text[:120]!r}",
        )

        # A JSON API must return RFC 8259 JSON. Pydantic v2 serialises float('inf') and
        # float('nan') as the bare tokens Infinity and NaN, which Python's own json module accepts
        # and every strict parser - including JSON.parse in the browser that consumes this -
        # rejects. `AssessmentPreview.confidence_score` is an unconstrained float, so this is
        # reachable rather than theoretical.
        if response.headers.get("content-type", "").startswith("application/json"):
            problem = _json_problem(response.text)
            if problem:
                invariant(
                    False,
                    f"{method} {path} -> {response.status_code}: {problem}",
                )


def _send(method, path, kind, body, header, text, payload):
    if kind == "multipart":
        filename = FILENAMES[header[3] % len(FILENAMES)]
        return _CLIENT.post(
            path,
            data={"learner_id": _path_value(header[2], text, LEARNER_ID)},
            files={"file": (filename, payload, "application/octet-stream")},
        )

    if kind == "query":
        return _CLIENT.get(path, params=_query_params(header, text))

    if kind == "path":
        return _CLIENT.request(method, path)

    # kind == "json". Two modes, because they attack different layers.
    if header[1] % 4 == 0:
        # RAW: the payload IS the body. Attacks the JSON parser and pydantic's coercion, and
        # should only ever produce 422.
        return _CLIENT.post(
            path, content=payload, headers={"content-type": "application/json"}
        )

    # INJECTED: a valid body with one field replaced. Attacks the handler, by getting past
    # validation with a value validation let through.
    mutated = dict(body)
    keys = sorted(mutated)
    key = keys[header[2] % len(keys)]
    mutated[key] = _coerce(mutated[key], text, header[3])

    # Serialised here rather than by passing `json=`, because httpx refuses to encode `inf` and
    # `nan` ("Out of range float values are not JSON compliant") and raises in the CLIENT - which
    # the engine correctly reported as a crash in our own frame, the second false finding this
    # target produced. `allow_nan=True` puts the bare `Infinity` / `NaN` tokens on the wire, which
    # is exactly what a hostile client sends and what the server's own float fields accept. Being
    # unable to send a value is not the same as the server being unable to receive it.
    return _CLIENT.post(
        path,
        content=json.dumps(mutated, allow_nan=True),
        headers={"content-type": "application/json"},
    )


def _coerce(sample, text: str, flavour: int):
    """A replacement value shaped roughly like the one it replaces.

    Type-aware on purpose. Dropping a string into an int field is rejected by pydantic before the
    handler runs, so a fuzzer that only ever substitutes strings tests the validator and never the
    code behind it. Matching the type is what gets the input past the door.
    """
    if isinstance(sample, bool):
        return flavour % 2 == 0
    if isinstance(sample, int):
        return INTERESTING_INTS[flavour % len(INTERESTING_INTS)]
    if isinstance(sample, float):
        return _as_float(text, flavour)
    if isinstance(sample, dict):
        try:
            parsed = json.loads(text)
        except Exception:  # noqa: BLE001
            return {"k": text[:256]}
        return parsed if isinstance(parsed, dict) else {"k": parsed}
    if isinstance(sample, list):
        return [chunk for chunk in text.split(",")[:16]]
    if sample is None:
        return None if flavour % 3 == 0 else text
    return text


def _as_float(text: str, flavour: int) -> float:
    specials = [0.0, -0.0, 1e308, -1e308, float("inf"), float("-inf"), float("nan")]
    try:
        return float(text.split()[0])
    except (ValueError, IndexError):
        return specials[flavour % len(specials)]


def _path_value(selector: int, text: str, known: str) -> str:
    """Either the seeded id or something derived from the input, percent-encoded.

    Always sending garbage would mean every request 404s before reaching anything; always sending
    the real id would leave path handling untested. The selector decides per input.

    THE ENCODING IS NOT OPTIONAL, and leaving it out produced the first false finding this target
    reported: a raw control character in the path makes httpx raise `InvalidURL` in the CLIENT,
    before a request is ever sent, and the engine dutifully filed it as a crash in our own
    fuzzer's frame. Percent-encoding puts the bytes on the wire, which is where they belong -
    what the server does with `%18` is a fact about the server, and that is the thing under test.
    `safe=""` because `/`, `?` and `#` would change the ROUTE rather than the parameter, and a
    finding against an endpoint we did not mean to call describes nothing.
    """
    if selector % 3 == 0 or not text:
        return known
    return quote(text[:200], safe="") or known


def _query_params(header, text: str) -> dict:
    """Params for GET /learners, whose page/per_page are the only bounded ones in the app.

    Included as a NEGATIVE CONTROL. The report can say the fuzzer failed to break the endpoint
    that validates its inputs and broke the ones that do not, which is a stronger claim than a
    list of failures alone.
    """
    return {
        "page": INTERESTING_INTS[header[1] % len(INTERESTING_INTS)],
        "per_page": INTERESTING_INTS[header[3] % len(INTERESTING_INTS)],
        "q": text[:500],
        "caseload": header[2] % 2 == 0,
    }


def _json_problem(text: str) -> str | None:
    """Why `text` is not RFC 8259 JSON, or None if it is fine.

    Two distinct defects share this check and must not share a message. A body containing the bare
    tokens `NaN` / `Infinity` parses in Python and fails in the browser; a body that is not JSON
    at all under a `application/json` header is a different bug with a different fix. Reporting
    both as "NaN or Infinity" would send whoever reads the finding to the wrong place.

    An empty body is not a defect: 204 and some error paths legitimately send nothing.
    """
    if not text.strip():
        return None

    def reject(constant):
        raise _NonStandardConstant(constant)

    try:
        json.loads(text, parse_constant=reject)
    except _NonStandardConstant as bad:
        return (
            f"body contains the non-RFC-8259 constant {bad.args[0]!r}, which Python's json "
            f"accepts and the browser's JSON.parse rejects"
        )
    except ValueError as bad:
        return f"body sent as application/json is not JSON: {bad}"
    return None


class _NonStandardConstant(ValueError):
    """Raised by the `parse_constant` hook so the NaN case is distinguishable from a syntax error.

    Subclasses ValueError only so a stray `except ValueError` elsewhere cannot swallow it silently
    while looking like it handled something else.
    """
