"""E2E use case TEMPLATE: "Generate a learner profile" (LLM-backed pipeline).

This is the pattern for use cases that touch the LLM. The default provider is
Ollama (absent in CI), so we swap in a deterministic fake provider via the
built-in seam `LLMApiClient.use_provider(...)` — no network, repeatable output.
Runs against the real project's data for the learner named by TEST_LEARNER_ID.

Skipped unless TEST_LEARNER_ID is set (in addition to the usual e2e secrets),
so it never fails on a project without suitable seed data. Copy this file as
the starting point for other LLM use cases (e.g. generate activity).
"""
import os

import pytest

pytestmark = pytest.mark.e2e


class _FakeLLM:
    """Deterministic stand-in implementing the LLMProvider protocol."""
    embed_dim = 768

    def complete(self, prompt, system=None, temperature=None, seed=None):
        return "FAKE_COMPLETION"

    def embed_many(self, texts, *, is_query=False):
        return [[0.0] * self.embed_dim for _ in texts]


@pytest.fixture
def stub_llm():
    from app.gateways.llm_client import LLMApiClient
    LLMApiClient.use_provider(_FakeLLM())
    yield
    LLMApiClient.use_provider(None)  # revert to the settings-configured backend


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_generate_profile_for_seeded_learner(client, access_token, stub_llm):
    learner_id = os.environ.get("TEST_LEARNER_ID")
    if not learner_id:
        pytest.skip("set TEST_LEARNER_ID to a learner in the test project to run this use case")

    resp = client.post(f"/profiles/{learner_id}", headers=_auth(access_token))

    assert resp.status_code == 200
    assert resp.json()["learner_id"] == learner_id
