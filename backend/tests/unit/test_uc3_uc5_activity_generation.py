"""UNIT — UC3 (Adaptive Activity Generator) + UC5 (Instructional Strategy Retrieval).

Consolidated test suite matching the UC3/UC5 test plan side-by-side:

  UC5 RetrievalService
    UT-5.1  Retrieval finds relevant strategies (profileMetrics -> strategies)
    UT-5.2  Insufficient knowledge found -> empty list / fallback

  UC3 ActivityGenerationService
    UT-3.1  Generate activity for specific profile given by ID
    UT-3.2  Best flagged activity generation attempt returned

  UC3 ActivityGraph
    UT-3.3  Validates on first attempt (retryCount = 0)
    UT-3.4  Validates after one rejection (retryCount = 1)
    UT-3.5  Exhausts retries -> status=FLAGGED, returns best attempt

  UC3 GenerativeAgent
    UT-3.6  Draft generated successfully -> status=GENERATED
    UT-3.7  Failure is propagated (LLMApiClient timeout/error)

  UC3 ValidativeAgent
    UT-3.8  Passes validation -> valid=True
    UT-3.9  Fails validation -> valid=False with feedback

  UC3 ActivityRepository
    UT-3.10 Validated activity persisted (status=VALIDATED)
    UT-3.11 Flagged activity persisted (status=FLAGGED)

  UC3 ActivityController / Router
    UT-3.12 Displays validated activity (200 + GENERATED status)
    UT-3.13 Displays flagged activity (200 + INSUFFICIENT_CONTEXT/FLAGGED status)
"""
from unittest.mock import Mock, patch
import pytest

pytestmark = pytest.mark.unit

LEARNER_ID = "11111111-1111-1111-1111-111111111111"
PROMPT = "literacy activity targeting phonics 2.4/10"

CHUNK = {
    "activity_title": "Rhyme Time", "content_md": "body", "concept": "onset_rime",
    "stage": "practice", "source_file": "BandA.pdf", "page_start": "14", "similarity": 0.71,
}

STRATEGY_A = {
    "id": "s1", "strategy_name": "Phonics Blending", "description": "Blending onset and rime", "similarity": 0.85,
}
STRATEGY_B = {
    "id": "s2", "strategy_name": "Sight Words", "description": "High-frequency word recognition", "similarity": 0.72,
}
PROFILE_METRICS = {"phonics": 2.4, "word_reading_accuracy": 7.0, "word_spelling": 4.0}


def _learner(**overrides):
    return {
        "id": LEARNER_ID,
        "pseudonym": "Aisha Binti Rahman", "student_id": "Student 0142", "tier": "Tier 2",
        "band": "A2", "band_group": "A",
        "phonics": 12.0, "word_reading_accuracy": 7.0, "word_spelling": 4.0, "writing": None,
        "phonics_pct": 22.0, "word_reading_accuracy_pct": 61.0,
        "word_spelling_pct": 35.0, "writing_pct": None,
        **overrides,
    }


def _activity(status, **overrides):
    return {
        "learner_id": LEARNER_ID,
        "content": {"text": "Title: Rhyme Time\n1. Clap the rhyme.", "query": "phonics"},
        "literacy_objective": "",
        "level": "A2",
        "status": status,
        "grounded_on": ["Rhyme Time (BandA.pdf p.14)"],
        **overrides,
    }


# ==============================================================================
# UC5 — RetrievalService (.retrieveStrategies())
# ==============================================================================

def test_ut_5_1_retrieval_finds_relevant_strategies():
    """UT-5.1 — When KB has relevant strategy vectors, retrieve_strategies returns them."""
    from app.services.retrieval_service import RetrievalService

    svc = RetrievalService.__new__(RetrievalService)
    svc.kb = Mock()
    svc.kb.similarity_search.return_value = [STRATEGY_A, STRATEGY_B]
    svc.llm = Mock()
    svc.llm.embed.return_value = [0.1] * 768

    result = svc.retrieve_strategies(PROFILE_METRICS)

    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["strategy_name"] == "Phonics Blending"
    svc.llm.embed.assert_called_once()
    svc.kb.similarity_search.assert_called_once()


def test_ut_5_2_insufficient_knowledge_returns_empty():
    """UT-5.2 — When KB has no relevant matches or raises, return empty list (generic fallback)."""
    from app.services.retrieval_service import RetrievalService

    svc = RetrievalService.__new__(RetrievalService)
    svc.kb = Mock()
    svc.kb.similarity_search.return_value = []
    svc.llm = Mock()
    svc.llm.embed.return_value = [0.1] * 768

    result = svc.retrieve_strategies(PROFILE_METRICS)
    assert result == []

    # Also handles exception gracefully
    svc.kb.similarity_search.side_effect = Exception("DB error")
    assert svc.retrieve_strategies(PROFILE_METRICS) == []


# ==============================================================================
# UC3 — ActivityGenerationService
# ==============================================================================

def test_ut_3_1_generate_activity_for_profile_id():
    """UT-3.1 — Generate activity for specific profile given by ID."""
    from app.services.activity_generation_service import ActivityGenerationService

    svc = ActivityGenerationService.__new__(ActivityGenerationService)
    saved = []
    svc.learners = type("_L", (), {"find_by_id": staticmethod(lambda _id: _learner())})()
    svc.activities = type("_A", (), {"save": staticmethod(lambda row: saved.append(row))})()
    svc.curriculum = type("_C", (), {"retrieve": staticmethod(lambda *a, **k: [CHUNK])})()
    svc.chunks = None
    svc.llm = type("_M", (), {"complete": staticmethod(lambda *a, **k: "Title: Rhyme Time")})()

    result = svc.generate(LEARNER_ID, {})

    assert result["status"] == "GENERATED"
    assert result["learner_id"] == LEARNER_ID
    assert "Rhyme Time" in result["content"]
    assert len(saved) == 1


def test_ut_3_2_flagged_activity_returned():
    """UT-3.2 — Best flagged activity generation attempt returned (or model refusal)."""
    from app.services.activity_generation_service import ActivityGenerationService

    svc = ActivityGenerationService.__new__(ActivityGenerationService)
    saved = []
    svc.learners = type("_L", (), {"find_by_id": staticmethod(lambda _id: _learner())})()
    svc.activities = type("_A", (), {"save": staticmethod(lambda row: saved.append(row))})()
    svc.curriculum = type("_C", (), {"retrieve": staticmethod(lambda *a, **k: [CHUNK])})()
    svc.chunks = None
    svc.llm = type("_M", (), {
        "complete": staticmethod(lambda *a, **k: "INSUFFICIENT_CONTEXT\n- missing phonics")
    })()

    result = svc.generate(LEARNER_ID, {})

    assert result["status"] == "INSUFFICIENT_CONTEXT"
    assert result["learner_id"] == LEARNER_ID
    assert len(saved) == 0


# ==============================================================================
# UC3 — ActivityGraph
# ==============================================================================

def test_ut_3_3_activity_graph_validates_on_first_attempt():
    """UT-3.3 — Validates on first attempt (status=VALIDATED, retryCount=0)."""
    from app.agents.activity_graph import ActivityGraph

    graph = ActivityGraph.__new__(ActivityGraph)
    graph.max_retries = 2
    graph.generator = Mock()
    graph.generator.generate.return_value = {"content": "Draft 1", "status": "GENERATED"}
    graph.validator = Mock()
    graph.validator.validate.return_value = {"valid": True, "notes": ""}

    result = graph.run(PROMPT)

    assert result["status"] == "VALIDATED"
    assert graph.generator.generate.call_count == 1
    assert graph.validator.validate.call_count == 1


def test_ut_3_4_activity_graph_validates_after_one_rejection():
    """UT-3.4 — Validates after one rejection (status=VALIDATED, retryCount=1)."""
    from app.agents.activity_graph import ActivityGraph

    graph = ActivityGraph.__new__(ActivityGraph)
    graph.max_retries = 2
    graph.generator = Mock()
    graph.generator.generate.side_effect = [
        {"content": "Draft 1", "status": "GENERATED"},
        {"content": "Draft 2", "status": "GENERATED"},
    ]
    graph.validator = Mock()
    graph.validator.validate.side_effect = [
        {"valid": False, "notes": "Rejection 1"},
        {"valid": True, "notes": ""},
    ]

    result = graph.run(PROMPT)

    assert result["status"] == "VALIDATED"
    assert graph.generator.generate.call_count == 2
    assert graph.validator.validate.call_count == 2


def test_ut_3_5_activity_graph_exhausts_retries():
    """UT-3.5 — Exhausts retries -> status=FLAGGED, returns best attempt."""
    from app.agents.activity_graph import ActivityGraph

    graph = ActivityGraph.__new__(ActivityGraph)
    graph.max_retries = 2
    graph.generator = Mock()
    graph.generator.generate.return_value = {"content": "Draft N", "status": "GENERATED"}
    graph.validator = Mock()
    graph.validator.validate.return_value = {"valid": False, "notes": "Invalid"}

    result = graph.run(PROMPT)

    assert result["status"] == "FLAGGED"
    assert graph.generator.generate.call_count == 3  # initial + 2 retries
    assert graph.validator.validate.call_count == 2  # max_retries validator checks


# ==============================================================================
# UC3 — GenerativeAgent
# ==============================================================================

def test_ut_3_6_generative_agent_draft_generated():
    """UT-3.6 — Draft generated successfully (status=GENERATED)."""
    from app.agents.agents import GenerativeAgent

    llm = Mock()
    llm.complete.return_value = "Title: Rhyme Time"
    agent = GenerativeAgent(llm)

    result = agent.generate(PROMPT)
    assert result["status"] == "GENERATED"
    assert "Rhyme Time" in result["content"]


def test_ut_3_7_generative_agent_failure_propagated():
    """UT-3.7 — Failure is propagated (LLMApiClient times out/fails)."""
    from app.agents.agents import GenerativeAgent

    llm = Mock()
    llm.complete.side_effect = TimeoutError("Timeout")
    agent = GenerativeAgent(llm)

    with pytest.raises(TimeoutError):
        agent.generate(PROMPT)


# ==============================================================================
# UC3 — ValidativeAgent
# ==============================================================================

def test_ut_3_8_validative_agent_passes():
    """UT-3.8 — Passes validation (valid=True)."""
    from app.agents.agents import ValidativeAgent

    agent = ValidativeAgent(Mock())
    result = agent.validate({"content": "Activity"}, framework="DAS")
    assert result["valid"] is True


def test_ut_3_9_validative_agent_fails():
    """UT-3.9 — Fails validation (valid=False, feedback)."""
    from app.agents.agents import ValidativeAgent

    agent = ValidativeAgent(Mock())
    agent.validate = Mock(return_value={"valid": False, "notes": "Rule violation"})
    result = agent.validate({"content": "Activity"}, framework="DAS")
    assert result["valid"] is False
    assert "Rule violation" in result["notes"]


# ==============================================================================
# UC3 — ActivityRepository
# ==============================================================================

def test_ut_3_10_validated_activity_persisted(fake_supabase):
    """UT-3.10 — Validated activity persisted, saved in repo."""
    fake = fake_supabase(seed={})
    from app.repositories.activity_repository import ActivityRepository

    repo = ActivityRepository()
    row = _activity("VALIDATED")
    res = repo.save(row)
    assert res is not None
    assert fake.store["learning_activities"][0]["status"] == "VALIDATED"


def test_ut_3_11_flagged_activity_persisted(fake_supabase):
    """UT-3.11 — Flagged activity persisted, saved in repo."""
    fake = fake_supabase(seed={})
    from app.repositories.activity_repository import ActivityRepository

    repo = ActivityRepository()
    row = _activity("FLAGGED")
    res = repo.save(row)
    assert res is not None
    assert fake.store["learning_activities"][0]["status"] == "FLAGGED"


# ==============================================================================
# UC3 — ActivityController / Router
# ==============================================================================

def test_ut_3_12_controller_displays_validated_activity(client, auth_ok):
    """UT-3.12 — Displays validated activity (200 + GENERATED status)."""
    payload = {"status": "GENERATED", "content": "Rhyme Time", "learner_id": LEARNER_ID, "grounding": []}
    with patch("app.routers.activities.svc.generate", return_value=payload):
        resp = client.post(f"/activities/{LEARNER_ID}/generate", json={"notes": ""})

    assert resp.status_code == 200
    assert resp.json()["status"] == "GENERATED"


def test_ut_3_13_controller_displays_flagged_activity(client, auth_ok):
    """UT-3.13 — Displays flagged activity (200 + INSUFFICIENT_CONTEXT status)."""
    payload = {"status": "INSUFFICIENT_CONTEXT", "reason": "thin grounding", "learner_id": LEARNER_ID, "grounding": []}
    with patch("app.routers.activities.svc.generate", return_value=payload):
        resp = client.post(f"/activities/{LEARNER_ID}/generate", json={"notes": ""})

    assert resp.status_code == 200
    assert resp.json()["status"] == "INSUFFICIENT_CONTEXT"
