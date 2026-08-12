"""UNIT — UC5 Retrieve Instructional Strategy (included by UC3).

    AB5.1  CurriculumRetrievalService.retrieve()        UT-5.5 .. UT-5.9
    AB5.2  LLMApiClient.embed() / embed_many()          UT-5.10, UT-5.11
    AB5.3  CurriculumRepository.*match_curriculum()     UT-5.12, UT-5.13
    AB5.4  curriculum_repository._with_alt()            UT-5.14, UT-5.15
    AB5.5  llm_client._unit()                           UT-5.16, UT-5.17
    AB5.6  OllamaProvider._task_prefix()                UT-5.18

**UC5 HAD NO UNIT TIER.** `integration/test_uc5_retrieve_strategy.py` covers IT-5.1, IT-5.3 and
IT-5.4 over a faked Supabase; nothing tested these units in isolation. The IDs start at UT-5.5
so they do not collide with the plan's IT numbering conventions, and because UT-5.1 – UT-5.4 are
reserved for the `RetrievalService` / `KnowledgeBaseRepository` lifelines the UC5 sequence
diagram names. Those are diagram names for the classes below: the code calls them
`CurriculumRetrievalService` / `CurriculumRepository`, over `curriculum_chunks` rather than an
`instructional_strategies` corpus. Mapping documented here rather than renaming either side.

Everything is mocked or pure. No Supabase, no HTTP, no embedding provider. What is under test is
the DISPATCH and the PAYLOAD SHAPE — the two places where a mistake returns confident nonsense
instead of an error.
"""
import math
from unittest.mock import Mock

import pytest

from app.gateways.llm_client import LLMApiClient, _unit
from app.repositories.curriculum_repository import _with_alt
from app.services.curriculum_retrieval_service import CurriculumRetrievalService

pytestmark = pytest.mark.unit

CHUNK = {"title": "Blending CVC words", "concept": "phonics", "stage": "1", "similarity": 0.81}


@pytest.fixture
def service():
    """The real service with both collaborators replaced."""
    svc = CurriculumRetrievalService()
    svc.repo = Mock()
    svc.llm = Mock()
    svc.llm.embed.return_value = [0.1] * 768
    svc.repo.hybrid_match_curriculum.return_value = [CHUNK]
    svc.repo.match_curriculum.return_value = [CHUNK]
    return svc


# --------------------------------------------------------------------------- #
# AB5.1 — retrieve(): which RPC, with what, and what happens when it fails
# --------------------------------------------------------------------------- #
def test_ut_5_5_the_default_path_is_hybrid_not_pure_vector(service):
    """UT-5.5: hybrid (vector + full-text, fused by RRF) is the default.

    The distinction is not cosmetic. Curriculum chunks are short and full of exact terms a
    therapist searches by ("CVC", "digraph"), which lexical matching finds and a 768-dim vector
    can miss entirely. Silently defaulting to pure vector would degrade every real retrieval
    without failing anything.
    """
    service.retrieve("blending cvc words")

    service.repo.hybrid_match_curriculum.assert_called_once()
    service.repo.match_curriculum.assert_not_called()


def test_ut_5_6_vector_only_selects_the_pure_semantic_rpc(service):
    """UT-5.6: `vector_only=True` picks the other RPC — the A/B and fallback path."""
    service.retrieve("blending cvc words", vector_only=True)

    service.repo.match_curriculum.assert_called_once()
    service.repo.hybrid_match_curriculum.assert_not_called()


def test_ut_5_7_the_query_is_embedded_as_a_query_not_a_document(service):
    """UT-5.7: `is_query=True`, which providers with asymmetric retrieval act on.

    nomic-embed-text is trained with `search_query:` / `search_document:` prefixes and
    gemini-embedding-001 honours `taskType`. Embedding a search as though it were a stored
    document is the classic RAG own-goal: it returns results, just worse ones, so nothing fails
    and nobody notices.
    """
    service.retrieve("blending cvc words")

    service.llm.embed.assert_called_once_with("blending cvc words", is_query=True)


def test_ut_5_8_every_filter_reaches_the_rpc_unchanged(service):
    """UT-5.8: the metadata filters are CORRECTNESS, not ranking.

    They run in the RPC's WHERE clause; the vector only orders whatever survives them. A filter
    dropped here does not narrow the results, it widens them — a band-A learner gets handed
    band-C material and the similarity score still looks healthy.
    """
    service.retrieve(
        "blending", band="A1", band_group="A", concept="phonics", stage="2", k=7,
    )

    kwargs = service.repo.hybrid_match_curriculum.call_args.kwargs
    assert kwargs["band"] == "A1"
    assert kwargs["band_group"] == "A"
    assert kwargs["concept"] == "phonics"
    assert kwargs["stage"] == "2"
    assert kwargs["match_count"] == 7          # `k` is renamed at this boundary
    assert kwargs["use_alt"] is False

    # The hybrid RPC also needs the RAW TEXT for its full-text arm, not just the vector.
    args = service.repo.hybrid_match_curriculum.call_args.args
    assert args[0] == service.llm.embed.return_value
    assert args[1] == "blending"


def test_ut_5_9_a_repository_failure_becomes_an_empty_result(service):
    """UT-5.9: retrieve() swallows every exception and returns [].

    DOCUMENTING A DELIBERATE TRADE-OFF, AND ITS COST. The bare `except Exception` covers an
    empty corpus, a filter that matched nothing, and Supabase being unreachable — three states
    that are genuinely indistinguishable to a caller that only wants chunks. It also means a
    missing migration (PGRST202 from an unknown RPC overload) reads as "nothing matched".

    That is survivable ONLY because the layer above treats an empty result as fatal: UC3's
    MIN_SIMILARITY gate refuses to generate without grounding, so a swallowed outage becomes a
    refusal rather than an ungrounded activity. This test pins the swallow so the guard above it
    is never removed on the assumption that this one raises.
    """
    service.repo.hybrid_match_curriculum.side_effect = RuntimeError("PGRST202: no such function")

    assert service.retrieve("blending") == []


def test_ut_5_9b_an_embedding_failure_is_not_swallowed(service):
    """UT-5.9: the `try` starts AFTER the embed call, so a dead embedder still raises.

    The asymmetry is right: an empty corpus is an ordinary answer, but an embedding provider
    that is down is a misconfiguration, and returning [] for it would look like a curriculum
    with no match for anything.
    """
    service.llm.embed.side_effect = ConnectionError("ollama not running")

    with pytest.raises(ConnectionError):
        service.retrieve("blending")


# --------------------------------------------------------------------------- #
# AB5.2 — the embedding facade
# --------------------------------------------------------------------------- #
@pytest.fixture
def fake_provider(monkeypatch):
    """Install a stand-in provider on the LLMApiClient singleton.

    `monkeypatch.setattr` on `_override` rather than `use_provider()`: the class is a
    `__new__`-based singleton and `_override` is CLASS-level, so a leak contaminates every later
    test in the session. monkeypatch's teardown is unconditional, where a `try/finally` only
    protects code that got as far as entering the `try`. Setting the attribute directly also
    skips the `cache_clear()` calls `use_provider` makes, which are unnecessary here because the
    builders are never consulted while an override is set.
    """
    provider = Mock(embed_dim=768)
    monkeypatch.setattr(LLMApiClient, "_override", provider)
    return provider


def test_ut_5_10_embed_delegates_to_the_batch_call(fake_provider):
    """UT-5.10: embed() is embed_many() of one, so both share a single code path."""
    fake_provider.embed_many.return_value = [[0.5, 0.5]]

    assert LLMApiClient().embed("hello", is_query=True) == [0.5, 0.5]
    fake_provider.embed_many.assert_called_once_with(["hello"], is_query=True)


def test_ut_5_11_an_empty_batch_never_reaches_the_provider(fake_provider):
    """UT-5.11: embed_many([]) short-circuits.

    The ingest batches chunks, and a final empty batch is ordinary. Providers bill per request
    and some reject an empty payload outright, so this is the difference between a no-op and a
    400 at the end of every ingest run.
    """
    assert LLMApiClient().embed_many([]) == []
    fake_provider.embed_many.assert_not_called()


# --------------------------------------------------------------------------- #
# AB5.3 / AB5.4 — the repository and its RPC payload
# --------------------------------------------------------------------------- #
def test_ut_5_12_the_repository_forwards_to_the_vector_rpc(monkeypatch):
    """UT-5.12: match_curriculum passes its arguments through positionally, in order."""
    import app.repositories.curriculum_repository as repo_mod

    captured = {}
    monkeypatch.setattr(repo_mod, "match_curriculum_rpc",
                        lambda *a, **kw: captured.update(args=a, kwargs=kw) or [CHUNK])

    result = repo_mod.CurriculumRepository().match_curriculum(
        [0.1, 0.2], band="A1", band_group="A", concept="phonics", stage="2", match_count=5,
    )

    assert result == [CHUNK]
    assert captured["args"] == ([0.1, 0.2], "A1", "A", "phonics", "2", 5, False)


def test_ut_5_13_the_hybrid_rpc_carries_the_query_text_and_the_rrf_defaults(monkeypatch):
    """UT-5.13: the hybrid arm needs the text as well as the vector.

    Its RRF fusion ranks a full-text result set against a semantic one; without `query_text`
    the lexical arm has nothing to search and the "hybrid" degenerates to pure vector while
    still reporting itself as hybrid.
    """
    import app.repositories.curriculum_repository as repo_mod

    captured = {}
    monkeypatch.setattr(repo_mod, "hybrid_match_curriculum_rpc",
                        lambda *a, **kw: captured.update(args=a) or [CHUNK])

    repo_mod.CurriculumRepository().hybrid_match_curriculum(
        [0.1, 0.2], "blending cvc", band_group="A", match_count=3,
    )

    vector, text, band, band_group, concept, stage, count, rrf_k, ftw, sw, use_alt = captured["args"]
    assert (vector, text) == ([0.1, 0.2], "blending cvc")
    assert (band_group, count) == ("A", 3)
    # Equal weights and rrf_k=50 are the tuned defaults; a caller that omits them must get them.
    assert (rrf_k, ftw, sw) == (50, 1.0, 1.0)


def test_ut_5_14_use_alt_is_omitted_from_the_payload_when_off():
    """UT-5.14: THE POSTGREST OVERLOAD TRAP.

    PostgREST resolves an overloaded function by the EXACT SET of argument names supplied, so
    sending `use_alt: false` to a project that has not run the embedding_alt migration raises
    PGRST202 — which retrieve() then swallows into an empty result (UT-5.9). The symptom is a
    curriculum that matches nothing, with no error anywhere. Omitting the default is what keeps
    every production path working against both schema versions.
    """
    assert _with_alt({"match_count": 3}, False) == {"match_count": 3}
    assert "use_alt" not in _with_alt({"match_count": 3}, False)


def test_ut_5_15_use_alt_is_added_only_when_on():
    """UT-5.15: the evaluation harness is the one caller that opts in, and it gets the key."""
    assert _with_alt({"match_count": 3}, True) == {"match_count": 3, "use_alt": True}


# --------------------------------------------------------------------------- #
# AB5.5 / AB5.6 — the pure helpers underneath
# --------------------------------------------------------------------------- #
def test_ut_5_16_a_vector_is_l2_normalised():
    """UT-5.16: ‖v‖ == 1 afterwards, so cosine similarity is a plain dot product.

    Matryoshka models return UNNORMALISED vectors when truncated below their native width
    (gemini-embedding-001 at 768 arrives with ‖v‖ ≈ 0.59). pgvector's `<=>` normalises
    internally so ranking survives either way, but anything reading the raw vector — an offline
    eval, a dot-product index — silently would not.
    """
    result = _unit([3.0, 4.0])

    assert result == pytest.approx([0.6, 0.8])
    assert math.sqrt(sum(x * x for x in result)) == pytest.approx(1.0)


def test_ut_5_17_a_zero_vector_is_returned_unchanged_rather_than_dividing_by_zero():
    """UT-5.17: ‖v‖ == 0 is the one input that has no unit form.

    Returning it untouched keeps a degenerate embedding from taking down the whole ingest batch
    it happens to sit in.
    """
    assert _unit([0.0, 0.0, 0.0]) == [0.0, 0.0, 0.0]


@pytest.mark.parametrize("is_query", [True, False])
def test_ut_5_18_task_prefixes_are_off_by_default(is_query):
    """UT-5.18: no prefix either side, because the STORED CORPUS carries none.

    nomic-embed-text is trained to expect `search_query:` / `search_document:` and omitting them
    measurably degrades retrieval, so switching them on looks like free accuracy. It is not:
    prefixing only the query side pairs a prefixed query against unprefixed documents, which is
    worse than the consistent-but-suboptimal state we are in. The flag and the corpus have to
    move together, and this test is what fails if someone flips only the flag.
    """
    from app.gateways.llm_client import OllamaProvider

    assert OllamaProvider()._task_prefix(is_query) == ""


@pytest.mark.parametrize("is_query,expected", [(True, "search_query: "), (False, "search_document: ")])
def test_ut_5_18b_the_prefixes_are_asymmetric_once_enabled(monkeypatch, is_query, expected):
    """UT-5.18: with the flag on, a query and a document are prefixed DIFFERENTLY.

    Pins the pairing for whoever runs the deferred re-embedding experiment: getting these two
    the wrong way round is silent, and halves retrieval quality.
    """
    from app.core.config import settings
    from app.gateways.llm_client import OllamaProvider

    monkeypatch.setattr(settings, "ollama_use_task_prefixes", True)

    assert OllamaProvider()._task_prefix(is_query) == expected
