"""E2E use case: UC3 "Generate Adaptive Learning Activity" (includes UC5 retrieval).

Boundary to boundary through the HTTP API against the REAL Supabase test project with a real JWT —
the pattern from test_uc_generate_profile.py. The one thing that cannot be real in CI is the LLM
(no Ollama), so a deterministic provider is swapped in via `LLMApiClient.use_provider(...)`, the
same compromise the template documents. Retrieval still runs against the real curriculum_chunks
corpus; only the embedder and the writer/reviewer models are stubbed.

Skipped unless the e2e secrets are present (see conftest: client, access_token) plus a learner id.

WHY E2E-3.1 ASSERTS "A VALID OUTCOME" RATHER THAN A SPECIFIC ACTIVITY. With a stubbed embedder the
query vector cannot meaningfully match the real corpus, so whether the similarity gate passes is not
deterministic. Both UC3 endings are correct — a VALIDATED/GENERATED activity, or a documented
refusal — so E2E-3.1 proves the full pipeline ran boundary-to-boundary and returned a well-formed
status. E2E-3.2 is the deterministic half: a learner with no marks is refused BEFORE retrieval or
the model, needing no real LLM at all.
"""
import os

import pytest

from app.prompts.activity_prompts import VALIDATION_SYSTEM_PROMPT

pytestmark = pytest.mark.e2e


class _FakeLLM:
    """Deterministic stand-in implementing the LLMProvider protocol.

    Dispatches on `system`: the reviewer (VALIDATION_SYSTEM_PROMPT) gets a JSON pass verdict so the
    generate -> validate loop can reach VALIDATED; every other call is the writer and gets a draft.
    """
    embed_dim = 768

    def complete(self, prompt, system=None, temperature=None, seed=None):
        if system == VALIDATION_SYSTEM_PROMPT:
            return '{"valid": true}'
        return "Rhyme Time\n\n1. Clap the onset.\n2. Blend the rime.\n3. Say the word."

    def embed_many(self, texts, *, is_query=False):
        return [[0.1] * self.embed_dim for _ in texts]


@pytest.fixture
def stub_llm():
    from app.gateways.llm_client import LLMApiClient
    LLMApiClient.use_provider(_FakeLLM())
    yield
    LLMApiClient.use_provider(None)  # revert to the settings-configured backend


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_generate_activity_full_flow(client, access_token, stub_llm):
    """E2E-3.1: the operational flow. Posting the generate request for a seeded learner runs the
    whole stack — profile -> query -> retrieval (UC5) -> generate/validate -> response — and comes
    back well-formed. The outcome may be a validated activity OR a documented refusal (see header);
    the assertion is a valid status and the learner echoed back, not a specific activity."""
    learner_id = os.environ.get("TEST_LEARNER_ID")
    if not learner_id:
        pytest.skip("set TEST_LEARNER_ID to a learner in the test project to run this use case")

    resp = client.post(
        f"/activities/{learner_id}/generate", json={}, headers=_auth(access_token),
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] in ("GENERATED", "VALIDATED", "FLAGGED", "INSUFFICIENT_CONTEXT")
    assert body["learner_id"] == learner_id
    # Retrieval always reports its outcome, on success and on refusal alike.
    assert "grounding" in body and "query" in body


def test_generate_activity_refuses_without_scores(client, access_token, stub_llm):
    """E2E-3.2: the alternative flow, deterministic and LLM-free. A learner with no DIAL marks is
    refused before retrieval or the model — status INSUFFICIENT_CONTEXT, no activity produced."""
    learner_id = os.environ.get("TEST_UNSCORED_LEARNER_ID")
    if not learner_id:
        pytest.skip("set TEST_UNSCORED_LEARNER_ID to a learner that has no DIAL marks")

    resp = client.post(
        f"/activities/{learner_id}/generate", json={}, headers=_auth(access_token),
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "INSUFFICIENT_CONTEXT"
