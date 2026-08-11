"""INTEGRATION — UC3 Generate Adaptive Learning Activity. Call-graph, bottom-up.

UC3 <<includes>> UC5: `generate()` CALLS `CurriculumRetrievalService.retrieve()`, which is tested
on its own in test_uc5_retrieve_strategy.py (levels 1-2). This file picks up above it.

    Level 4   ActivityController  --generate(learner_id, params)-->        [HTTP boundary]
    Level 3   ActivityGenerationService  --find_by_id-->        LearnerRepository
                                         --retrieve-->          CurriculumRetrievalService (UC5)
                                         --run-->               ActivityGraph
                                         --save-->              ActivityRepository
    Level 2   ActivityGraph  --generate-->  GenerativeAgent  --complete-->  LLMApiClient
                             --validate-->  ValidativeAgent  --complete-->  LLMApiClient
    (below)   the two boundaries: Supabase (faked RPC + tables) and the LLM (faked provider)

Only the boundaries are faked. Everything from the controller down through the service, the
retrieval it includes, the graph and both agents, and every repository is REAL code. The learner
profile, the curriculum corpus and the saved activity all live in FakeSupabase; the embedder, the
writer and the reviewer are the one faked provider.

THE DIAGRAM AND THE CODE NOW AGREE. This file previously carried a note that the UC3 sequence
diagram routed generation through ActivityGraph -> GenerativeAgent -> ValidativeAgent while the
code called llm.complete() directly with agents.py stubbed. That is fixed: the loop is wired, so
the agent lifelines above are real edges and are exercised here rather than tested in isolation.
"""
import pytest

from app.agents.agents import GenerativeAgent
from app.gateways.llm_client import LLMApiClient
from app.prompts.activity_prompts import VALIDATION_SYSTEM_PROMPT
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
    """A curriculum_chunks row. `similarity` decides the guardrail-1 gate.

    The default 0.70 clears the calibrated MIN_SIMILARITY (0.67) with 0.03 to spare. Cases that
    want a refusal pass 0.30 explicitly. Both sit well clear of the gate on purpose — seeding a
    value near it would make these tests fail the next time the gate is re-derived for a new
    embedder, which is a calibration change, not a regression in this call graph.
    """
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
    """Stands in for every LLM role this call graph needs: the embedder, the WRITER and the REVIEWER.

    THE FAKE DISPATCHES ON `system`. Since UC3 routes through ActivityGraph the same client is
    called twice per attempt with two different system prompts, and one canned string cannot serve
    both roles — handed back to the reviewer, a draft activity is unreadable as a JSON verdict,
    which correctly fails closed and flags every activity in the suite. So: writers get
    `completion`, reviewers get the next entry in `verdicts`.

    `verdicts` is consumed in order and the last entry repeats, which is what lets a case say
    "rejected once, then accepted" without knowing how many times the loop will ask.

    `complete_calls` still records EVERY call, so the guardrail tests that assert the LLM edge was
    never taken keep working unchanged; `draft_calls` / `review_calls` split them by role for the
    loop tests, which care how many times each agent ran.
    """
    embed_dim = 3
    embedding_model = "fake-embed"

    DRAFT = "Rhyme Time\n\n1. Clap the onset.\n2. Blend the rime.\n3. Say the word."
    PASS = '{"valid": true}'
    FAIL = '{"valid": false, "notes": "step 2 uses rimes that are in none of the grounding pages"}'

    def __init__(self):
        self.completion = self.DRAFT
        self.verdicts = [self.PASS]
        self.complete_calls = []
        self.draft_calls = []
        self.review_calls = []

    def embed_many(self, texts, is_query=False):
        # is_query mirrors the real provider contract (query vs document embeddings); the fake
        # ignores it but must ACCEPT it, or the real LLMApiClient.embed(..., is_query=...) call
        # fails with a TypeError once this branch merges main.
        return [[0.1, 0.2, 0.3] for _ in texts]

    def complete(self, prompt, system=None, temperature=None, seed=None):
        self.complete_calls.append(prompt)
        if system == VALIDATION_SYSTEM_PROMPT:
            self.review_calls.append(prompt)
            return self.verdicts[min(len(self.review_calls) - 1, len(self.verdicts) - 1)]
        self.draft_calls.append(prompt)
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
    """IT-3.1: the happy path end to end — profile -> query -> retrieve (UC5) -> prompt -> graph
    (write + review) -> save, with no application code mocked. The reviewer passes it on the first
    attempt, so it returns VALIDATED with retry_count 0 and leaves a row behind."""
    fake = fake_supabase(seed={
        "learners": [_learner()],
        "curriculum_chunks": [_chunk("a1", "A1", similarity=0.70)],
    })

    out = ActivityGenerationService().generate(LEARNER_ID, {})

    assert out["status"] == "VALIDATED"
    assert out["content"] == fake_llm.completion         # the model's text, carried through
    assert out["learner_id"] == LEARNER_ID
    assert out["grounding"][0]["title"] == "Chunk a1"    # the retrieved chunk, summarised
    assert out["retry_count"] == 0                       # passed review first time
    # The postcondition is a stored activity, not just a response.
    assert len(fake.store["learning_activities"]) == 1
    assert fake.store["learning_activities"][0]["status"] == "VALIDATED"
    # Both agents ran exactly once: one draft written, one verdict returned.
    assert len(fake_llm.draft_calls) == 1
    assert len(fake_llm.review_calls) == 1


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
        "curriculum_chunks": [_chunk("a1", "A1", similarity=0.30)],  # well under the gate
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
# The validate/retry loop, through the whole service stack.
#
# IDs: the PM3 plan numbers these IT-3.2 and IT-3.3, but this file already assigned those to the
# two guardrail cases above, which were written first. They CONTINUE the sequence here rather than
# renumbering passing tests — the same convention tests/README.md used for UC2's clustering IDs.
# The graph's own arithmetic (retry_count, feedback text, fail-closed) is unit-tested in
# unit/test_uc3_activity_graph.py; what these add is that it survives the real service, the real
# repositories and the real prompt builders.
# --------------------------------------------------------------------------- #
def test_it_3_8_a_rejected_draft_is_reprompted_and_persisted_as_validated(fake_supabase, fake_llm):
    """IT-3.8 (plan IT-3.2/3.3): the reviewer rejects once, the writer is reprompted WITH the
    notes, and the accepted second draft is what gets stored — with retry_count 1 on the row."""
    fake = fake_supabase(seed={
        "learners": [_learner()],
        "curriculum_chunks": [_chunk("a1", "A1", similarity=0.70)],
    })
    fake_llm.verdicts = [_FakeLLM.FAIL, _FakeLLM.PASS]

    out = ActivityGenerationService().generate(LEARNER_ID, {})

    assert out["status"] == "VALIDATED"
    assert out["retry_count"] == 1
    assert len(fake_llm.draft_calls) == 2
    assert "rimes that are in none of the grounding pages" in fake_llm.draft_calls[1]
    row = fake.store["learning_activities"][0]
    assert row["status"] == "VALIDATED"
    assert row["retry_count"] == 1
    # One row, not one per attempt — a rejected draft is not an activity.
    assert len(fake.store["learning_activities"]) == 1


def test_it_3_9_an_unfixable_draft_is_stored_flagged_for_a_therapist(fake_supabase, fake_llm):
    """IT-3.9 (plan IT-3.3): the reviewer never accepts. The activity is still SAVED — alt flow 6b
    surfaces the best attempt rather than discarding the work — but marked FLAGGED, with the
    reason the reviewer gave, so the therapist knows what to look at."""
    fake = fake_supabase(seed={
        "learners": [_learner()],
        "curriculum_chunks": [_chunk("a1", "A1", similarity=0.70)],
    })
    fake_llm.verdicts = [_FakeLLM.FAIL]          # rejects every time

    out = ActivityGenerationService().generate(LEARNER_ID, {})

    assert out["status"] == "FLAGGED"
    assert out["retry_count"] == 2               # ActivityGraph's default max_retries
    assert "rimes that are in none of the grounding pages" in out["review_notes"]
    row = fake.store["learning_activities"][0]
    assert row["status"] == "FLAGGED"
    assert row["retry_count"] == 2


def test_it_3_10_a_flagged_activity_reaches_the_dashboards_pending_review_count(
        fake_supabase, fake_llm):
    """IT-3.10: the point of persisting FLAGGED. `routers/dashboard.py` counts
    learning_activities with status FLAGGED for its Pending Review tile — a counter that could
    only ever read 0 while every row was written as GENERATED."""
    fake = fake_supabase(seed={
        "learners": [_learner()],
        "curriculum_chunks": [_chunk("a1", "A1", similarity=0.70)],
    })
    fake_llm.verdicts = [_FakeLLM.FAIL]

    ActivityGenerationService().generate(LEARNER_ID, {})

    flagged = [a for a in fake.store["learning_activities"] if a["status"] == "FLAGGED"]
    assert len(flagged) == 1


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
    assert resp.json()["status"] == "VALIDATED"
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
# GenerativeAgent over the REAL client seam.
#
# This used to carry a warning that the agent was not on the UC3 call path — that
# ActivityGenerationService called llm.complete() directly and nothing reached ActivityGraph. It
# is now reached on every generation, and the cases above exercise it through the service. What
# is left here is the narrower claim the others cannot make: that the agent works against the
# real LLMApiClient singleton (with only its provider swapped) rather than an injected double.
# Its own logic — empty completions, transport failures — is unit-tested in
# unit/test_uc3_activity_graph.py.
# --------------------------------------------------------------------------- #
def test_generative_agent_wraps_the_llm_completion(fake_llm):
    """IT-3.7: real GenerativeAgent over the real LLMApiClient (faked provider only). It sends the
    prompt to the model and wraps the completion as a GENERATED draft."""
    fake_llm.completion = "Rhyme Time\n\n1. Clap the onset."
    agent = GenerativeAgent(LLMApiClient())

    out = agent.generate("make a rhyming activity")

    assert out == {"content": "Rhyme Time\n\n1. Clap the onset.", "status": "GENERATED"}
    assert fake_llm.complete_calls == ["make a rhyming activity"]   # the prompt reached the model
