"""KnowledgeBaseRepository - pgvector similarity search over instructional
strategies (the ELL-MLP teaching-resource corpus)."""
from app.repositories.base import BaseRepository


class KnowledgeBaseRepository(BaseRepository):
    table = "instructional_strategies"

    def similarity_search(self, query_vector: list[float], k: int = 5) -> list[dict]:
        # TODO: call the `match_strategies` SQL function (see infra/schema.sql)
        return get_rpc(query_vector, k)


def get_rpc(query_vector, k):
    from app.core.supabase_client import get_supabase
    return (
        get_supabase()
        .rpc("match_strategies", {"query_embedding": query_vector, "match_count": k})
        .execute()
        .data
    )
