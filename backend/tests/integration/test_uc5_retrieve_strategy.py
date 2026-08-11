"""INTEGRATION — UC5 Retrieve Instructional Strategy (included by UC3). Call-graph, bottom-up.

The call graph is read off the UC3/UC5 sequence diagram, restricted to the CODE's real retrieval
path. The diagram names the UC5 lifelines `RetrievalService`/`KnowledgeBaseRepository`; the class
that ActivityGenerationService actually calls is `CurriculumRetrievalService`/`CurriculumRepository`
over the `curriculum_chunks` corpus, so that is what these tests exercise.

    Level 2   CurriculumRetrievalService --embed(query)------------> LLMApiClient
                                         --hybrid_match_curriculum--> CurriculumRepository
    Level 1   CurriculumRepository --rpc--> Supabase pgvector       (faked)
              LLMApiClient        --embed--> Embedding provider      (faked)

Only the boundary is faked. FakeSupabase now models the match_curriculum / hybrid_match_curriculum
RPCs: the metadata filters from the SQL `filtered` CTE are honoured, and rows are ranked by the
seeded `similarity` (a fake has no real vectors — the vector maths is e2e's job). Everything above
the RPC is real code.

Level 1 is the leaf (IT-5.1). Level 2 wires the real service over BOTH faked boundaries — the
Supabase RPC and the embedder (IT-5.3, IT-5.4).
"""
import pytest

from app.gateways.llm_client import LLMApiClient
from app.repositories.curriculum_repository import CurriculumRepository
from app.services.curriculum_retrieval_service import CurriculumRetrievalService

pytestmark = pytest.mark.integration

VECTOR = [0.1, 0.2, 0.3]  # any 3 floats — the fake RPC does not read the vector, only the filters


def _chunk(id, band, *, concept="action_predicate", stage="practice", similarity=0.7,
           doc_type="lesson_plan", source_file="2) A1.pdf"):
    """One curriculum_chunks row, shaped like real ingestion writes it: `band` is the fine band
    ('A1'/'A2'/'A3', or 'A' for the unlevelled chunks) and `source_file` is the PDF's filename
    (`path.name`, e.g. '2) A1.pdf'). `similarity` is what the faked RPC ranks on (see module note).
    """
    return {
        "id": id, "band": band, "concept": concept, "stage": stage,
        "similarity": similarity, "doc_type": doc_type,
        "activity_title": f"Chunk {id}", "content_md": "body",
        "source_file": source_file, "page_start": "14", "answer_key": None,
    }


# --------------------------------------------------------------------------- #
# Level 1 — the leaf: real CurriculumRepository over the faked pgvector RPC
# --------------------------------------------------------------------------- #
def test_hybrid_match_scopes_to_the_band_group(fake_supabase):
    """IT-5.1: a Band A retrieval reaches every A* chunk and NOTHING outside the group — the scope
    the SQL enforces in the `filtered` CTE (`left(band,1) = filter_band_group`). The out-of-group
    B1 row is seeded with a HIGHER similarity than either A row, so a fake that ignored the filter
    would rank it first and this test would fail — which is the point: the scope is real, not a
    no-op."""
    fake_supabase(seed={"curriculum_chunks": [
        _chunk("a1", "A1", similarity=0.90, source_file="2) A1.pdf"),                  # a band book
        _chunk("a-unlevelled", "A", similarity=0.80, source_file="14) Action predicate.pdf"),
        _chunk("b1", "B1", similarity=0.95, source_file="9) Action Predicate.pdf"),    # Band B
    ]})

    rows = CurriculumRepository().hybrid_match_curriculum(
        VECTOR, "rhyming words", band_group="A", match_count=5,
    )

    ids = [r["id"] for r in rows]
    assert ids == ["a1", "a-unlevelled"]   # both A*, ranked by similarity; B1 never appears


# --------------------------------------------------------------------------- #
# Level 2 — CurriculumRetrievalService added: real service + real repo,
#           only the two boundaries (Supabase RPC + the embedder) faked
# --------------------------------------------------------------------------- #
class _FakeEmbedder:
    """A stand-in LLM provider. Only `embed` is exercised by retrieval, but the provider protocol
    also declares complete/embed_dim, so both are present. The vector is arbitrary — the faked RPC
    does not read it (it ranks by the seeded `similarity`), so any fixed vector will do."""
    embed_dim = 3
    embedding_model = "fake-embed"

    def embed_many(self, texts, is_query=False):
        # is_query mirrors the real provider contract (query vs document embeddings); the fake
        # ignores it since it returns a fixed vector, but must ACCEPT it or the real
        # LLMApiClient.embed(..., is_query=...) call fails with a TypeError.
        return [[0.1, 0.2, 0.3] for _ in texts]

    def complete(self, prompt, system=None, temperature=None, seed=None):
        return ""


@pytest.fixture
def fake_llm():
    """Swap LLMApiClient's backend for the fake embedder, then REVERT it.

    use_provider() sets a CLASS-level override on the singleton, so without the teardown it would
    leak into every later test. This is why the fixture yields instead of returning — the code
    after `yield` is the cleanup.
    """
    provider = _FakeEmbedder()
    LLMApiClient.use_provider(provider)
    yield provider
    LLMApiClient.use_provider(None)


def test_retrieve_embeds_the_query_and_returns_band_scoped_chunks(fake_supabase, fake_llm):
    """IT-5.3: the real CurriculumRetrievalService over the real CurriculumRepository, with only
    the two boundaries faked. Proves the wiring the leaf test could not — retrieve() embeds the
    query, hands the vector to the repo, and returns the ranked, band-scoped chunks — with NO
    application code mocked in between."""
    fake_supabase(seed={"curriculum_chunks": [
        _chunk("a1", "A1", similarity=0.90, source_file="2) A1.pdf"),
        _chunk("a-unlevelled", "A", similarity=0.80, source_file="14) Action predicate.pdf"),
        _chunk("b1", "B1", similarity=0.95, source_file="9) Action Predicate.pdf"),
    ]})

    rows = CurriculumRetrievalService().retrieve("rhyming words", band_group="A", k=5)

    assert [r["id"] for r in rows] == ["a1", "a-unlevelled"]


def test_retrieve_uses_the_pure_vector_rpc_when_vector_only(fake_supabase, fake_llm):
    """IT-5.4: the `vector_only` flag must select the match_curriculum RPC (pure vector), not the
    default hybrid_match_curriculum. Asserted on WHICH RPC the boundary saw — the queries log —
    because the two are different Postgres functions and the branch has to pick the right one."""
    fake = fake_supabase(seed={"curriculum_chunks": [
        _chunk("a1", "A1", similarity=0.90, source_file="2) A1.pdf"),
    ]})

    CurriculumRetrievalService().retrieve("rhyming words", band_group="A", k=3, vector_only=True)

    assert ("match_curriculum", "rpc") in fake.queries
    assert ("hybrid_match_curriculum", "rpc") not in fake.queries
