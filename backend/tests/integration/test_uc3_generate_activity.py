"""INTEGRATION — UC3 Generate Adaptive Learning Activity. Call-graph, bottom-up.

UC3 <<includes>> UC5: `generate()` CALLS `CurriculumRetrievalService.retrieve()`, which is tested
on its own in test_uc5_retrieve_strategy.py (levels 1-2). This file picks up above it.

    Level 4   ActivityController  --generate(learner_id, params)-->        [HTTP boundary]
    Level 3   ActivityGenerationService  --find_by_id-->        LearnerRepository
                                         --retrieve-->          CurriculumRetrievalService (UC5)
                                         --complete-->          LLMApiClient
                                         --save-->              ActivityRepository
    (below)   the two boundaries: Supabase (faked RPC + tables) and the LLM (faked provider)

Only the boundaries are faked. Everything from the controller down through the service, the
retrieval it includes, and every repository is REAL code. The learner profile, the curriculum
corpus and the saved activity all live in FakeSupabase; the embedder and the completion model are
the one faked provider.

NOTE ON THE DIAGRAM: the UC3 sequence diagram routes generation through ActivityGraph ->
GenerativeAgent -> ValidativeAgent with a validate/retry loop. The CODE does not — generate()
calls llm.complete() directly with inline guardrails (agents.py is a stub). These tests follow the
code, so the call graph above has no agent lifelines. Flagged for the diagram/code reconciliation.
"""
import pytest

from app.agents.agents import GenerativeAgent
from app.gateways.llm_client import LLMApiClient
from app.services.activity_generation_service import ActivityGenerationService

pytestmark = pytest.mark.integration

LEARNER_ID = "11111111-1111-4111-8111-111111111111"


def _learner(**overrides):
    """A Band A learner with three marks (writing is None — band A never sits it). `band_group`
    'A' is what band_scope reads; the marks are what build_query turns into the retrieval query."""
    return {
        "id": LEARNER_ID, "pseudonym": "Aisha Binti Rahman", "tier": "Tier 2",
        "band": "A2", "band_group": "A",
        "phonics": 12.0, "word_reading_accuracy": 7.0, "word_spelling": 4.0, "writing": None,
        **overrides,
    }


def _chunk(id, band="A1", *, similarity=0.70, doc_type="lesson_plan"):
    """A curriculum_chunks row. `similarity` decides the guardrail-1 gate (MIN_SIMILARITY 0.50)."""
    return {
        "id": id, "band": band, "concept": "action_predicate", "stage": "practice",
        "similarity": similarity, "doc_type": doc_type,
        "activity_title": f"Chunk {id}", "content_md": "Clap the onset, then blend the rime.",
        "source_file": "2) A1.pdf", "page_start": "14", "answer_key": None,
    }


# --------------------------------------------------------------------------- #
# The faked LLM provider — embeddings AND completions
# --------------------------------------------------------------------------- #
class _FakeLLM:
    """Stands in for BOTH LLM roles retrieval+generation need. `completion` is settable per test so
    a case can make the model self-refuse; `complete_calls` records invocations so a guardrail test
    can prove the LLM edge was NOT taken."""
    embed_dim = 3
    embedding_model = "fake-embed"

    def __init__(self):
        self.completion = "Rhyme Time\n\n1. Clap the onset.\n2. Blend the rime.\n3. Say the word."
        self.complete_calls = []

    def embed_many(self, texts, is_query=False):
        # is_query mirrors the real provider contract (query vs document embeddings); the fake
        # ignores it but must ACCEPT it, or the real LLMApiClient.embed(..., is_query=...) call
        # fails with a TypeError once this branch merges main.
        return [[0.1, 0.2, 0.3] for _ in texts]

    def complete(self, prompt, system=None, temperature=None, seed=None):
        self.complete_calls.append(prompt)
        return self.completion


@pytest.fixture
def fake_llm():
    """Install the fake provider, then REVERT it — use_provider sets a class-level override on the
    singleton, so the teardown after `yield` is what stops it leaking into later tests."""
    provider = _FakeLLM()
    LLMApiClient.use_provider(provider)
    yield provider
    LLMApiClient.use_provider(None)


def _no_rpc(fake):
    """True if no retrieval RPC was issued — i.e. the AuthService -> retrieval edge was skipped."""
    return not any(op == "rpc" for _table, op in fake.queries)


# --------------------------------------------------------------------------- #
# Level 3 — ActivityGenerationService.generate, whole backend stack real
# --------------------------------------------------------------------------- #
def test_generate_grounds_the_activity_and_persists_it(fake_supabase, fake_llm):
    """IT-3.1: the happy path end to end — profile -> query -> retrieve (UC5) -> prompt -> LLM ->
    save, with no application code mocked. Returns GENERATED and leaves a row behind."""
    fake = fake_supabase(seed={
        "learners": [_learner()],
        "curriculum_chunks": [_chunk("a1", "A1", similarity=0.70)],
    })

    out = ActivityGenerationService().generate(LEARNER_ID, {})

    assert out["status"] == "GENERATED"
    assert out["content"] == fake_llm.completion         # the model's text, carried through
    assert out["learner_id"] == LEARNER_ID
    assert out["grounding"][0]["title"] == "Chunk a1"    # the retrieved chunk, summarised
    # The postcondition is a stored activity, not just a response.
    assert len(fake.store["learning_activities"]) == 1
    assert fake.store["learning_activities"][0]["status"] == "GENERATED"


def test_generate_refuses_when_the_learner_has_no_band(fake_supabase, fake_llm):
    """IT-3.2: guardrail 0. A learner with no band_group is refused BEFORE any retrieval or LLM
    call — the unscoped-retrieval edge (which could ground them in another band) is never taken."""
    fake = fake_supabase(seed={
        "learners": [_learner(band_group="")],
        "curriculum_chunks": [_chunk("a1", "A1", similarity=0.99)],  # plenty of grounding, unused
    })

    out = ActivityGenerationService().generate(LEARNER_ID, {})

    assert out["status"] == "INSUFFICIENT_CONTEXT"
    assert _no_rpc(fake)                                  # retrieve() never reached
    assert fake_llm.complete_calls == []                 # LLM never reached
    assert fake.store.get("learning_activities", []) == []  # nothing saved


def test_generate_refuses_when_grounding_is_thin(fake_supabase, fake_llm):
    """IT-3.3: guardrail 1. Retrieval runs, but the best similarity is below MIN_SIMILARITY, so the
    activity is refused WITHOUT spending an LLM call — and nothing is persisted."""
    fake = fake_supabase(seed={
        "learners": [_learner()],
        "curriculum_chunks": [_chunk("a1", "A1", similarity=0.30)],  # 0.30 < 0.50 gate
    })

    out = ActivityGenerationService().generate(LEARNER_ID, {})

    assert out["status"] == "INSUFFICIENT_CONTEXT"
    assert fake_llm.complete_calls == []                 # refused before the LLM edge
    assert fake.store.get("learning_activities", []) == []


def test_generate_refuses_when_the_model_self_refuses(fake_supabase, fake_llm):
    """IT-3.4: guardrail 2. Grounding passes the gate and the LLM IS called, but the model returns
    an INSUFFICIENT_CONTEXT signal — so the result is a refusal and is NOT saved as an activity."""
    fake = fake_supabase(seed={
        "learners": [_learner()],
        "curriculum_chunks": [_chunk("a1", "A1", similarity=0.70)],
    })
    fake_llm.completion = "INSUFFICIENT_CONTEXT — the retrieved pages do not cover this request."

    out = ActivityGenerationService().generate(LEARNER_ID, {})

    assert out["status"] == "INSUFFICIENT_CONTEXT"
    assert fake_llm.complete_calls != []                 # the LLM WAS called this time
    assert fake.store.get("learning_activities", []) == []  # but a refusal is not an activity


# --------------------------------------------------------------------------- #
# Level 4 — ActivityController added, through the HTTP boundary
# --------------------------------------------------------------------------- #
def test_generate_route_returns_a_generated_activity(client, auth_ok, fake_supabase, fake_llm):
    """IT-3.5: POST /activities/{id}/generate through the real router -> service -> retrieval ->
    repos -> fakes. 200 with the activity, and the row is persisted."""
    fake = fake_supabase(seed={
        "learners": [_learner()],
        "curriculum_chunks": [_chunk("a1", "A1", similarity=0.70)],
    })

    resp = client.post(f"/activities/{LEARNER_ID}/generate", json={})

    assert resp.status_code == 200
    assert resp.json()["status"] == "GENERATED"
    assert len(fake.store["learning_activities"]) == 1


def test_generate_route_surfaces_a_refusal_with_200(client, auth_ok, fake_supabase, fake_llm):
    """IT-3.6: a refusal is NOT an HTTP error — the route returns the service's dict as-is, so a
    thin-grounding refusal comes back 200 with status INSUFFICIENT_CONTEXT and saves nothing."""
    fake = fake_supabase(seed={
        "learners": [_learner()],
        "curriculum_chunks": [_chunk("a1", "A1", similarity=0.30)],
    })

    resp = client.post(f"/activities/{LEARNER_ID}/generate", json={})

    assert resp.status_code == 200
    assert resp.json()["status"] == "INSUFFICIENT_CONTEXT"
    assert fake.store.get("learning_activities", []) == []


# --------------------------------------------------------------------------- #
# GenerativeAgent — the diagram's generation lifeline, tested IN ISOLATION.
#
# IMPORTANT: this is NOT on the UC3 call path. ActivityGenerationService.generate() calls
# llm.complete() directly; GenerativeAgent is only referenced by ActivityGraph, which nothing in
# the app reaches. So these tests prove the agent's OWN behaviour (it exists on the sequence
# diagram) — they do NOT prove UC3 routes through it, because in code it does not. This is the
# diagram-vs-code divergence flagged in the module docstring; ValidativeAgent (a stub) and
# ActivityGraph (a LangGraph placeholder) are deliberately left untested until they are wired in.
# --------------------------------------------------------------------------- #
def test_generative_agent_wraps_the_llm_completion(fake_llm):
    """IT-3.7 (agent, isolated): real GenerativeAgent over the faked LLM. It sends the prompt to
    the model and wraps the completion as a GENERATED activity dict."""
    fake_llm.completion = "Rhyme Time\n\n1. Clap the onset."
    agent = GenerativeAgent(LLMApiClient())

    out = agent.generate("make a rhyming activity")

    assert out == {"content": "Rhyme Time\n\n1. Clap the onset.", "status": "GENERATED"}
    assert fake_llm.complete_calls == ["make a rhyming activity"]   # the prompt reached the model
