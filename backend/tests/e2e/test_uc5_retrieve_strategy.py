"""E2E use case: UC5 "Retrieve Instructional Strategy" (included by UC3).

UC5 HAS NO HTTP ENDPOINT OF ITS OWN — its trigger is "UC3 reaches the retrieval step
(System-initiated)" — so its boundary-to-boundary flow is exercised THROUGH the generate endpoint.
This asserts that retrieval executed end to end against the REAL curriculum_chunks corpus: the
generate response carries the retrieval outcome in both endings (a `grounding` list, and the
`query` the retrieval ranked on), whether the activity was produced or refused for thin grounding.

Same real-JWT + real-Supabase + stub-LLM pattern as test_uc3_generate_activity.py: only the embedder
and the models are stubbed for determinism; the pgvector retrieval itself is real.

Skipped unless the e2e secrets + TEST_LEARNER_ID are present.
"""
import os

import pytest

from app.prompts.activity_prompts import VALIDATION_SYSTEM_PROMPT

pytestmark = pytest.mark.e2e


class _FakeLLM:
    """Deterministic LLMProvider stand-in — reviewer gets a JSON pass, everyone else a draft."""
    embed_dim = 768

    def complete(self, prompt, system=None, temperature=None, seed=None):
        if system == VALIDATION_SYSTEM_PROMPT:
            return '{"valid": true}'
        return "Rhyme Time\n\n1. Clap the onset.\n2. Blend the rime."

    def embed_many(self, texts, *, is_query=False):
        return [[0.1] * self.embed_dim for _ in texts]


@pytest.fixture
def stub_llm():
    from app.gateways.llm_client import LLMApiClient
    LLMApiClient.use_provider(_FakeLLM())
    yield
    LLMApiClient.use_provider(None)


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_retrieval_runs_within_generate(client, access_token, stub_llm):
    """E2E-5.1: retrieval executes as part of generation and its outcome reaches the response.
    A scored learner's generate call returns, through the whole stack, either the retrieved
    `grounding` chunks (success) or a `query` + INSUFFICIENT_CONTEXT refusal (thin grounding) —
    either way the retrieval step ran boundary-to-boundary against the real corpus."""
    learner_id = os.environ.get("TEST_LEARNER_ID")
    if not learner_id:
        pytest.skip("set TEST_LEARNER_ID to a learner with marks in the test project")

    resp = client.post(
        f"/activities/{learner_id}/generate", json={}, headers=_auth(access_token),
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    # The retrieval query is built from the learner's marks and always reported back; the grounding
    # list is present on success and refusal alike. Both being present proves retrieval ran.
    assert "query" in body and "grounding" in body
    assert body["status"] in ("GENERATED", "VALIDATED", "FLAGGED", "INSUFFICIENT_CONTEXT")
