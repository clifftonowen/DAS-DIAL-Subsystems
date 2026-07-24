"""INTEGRATION level 1 (bottom of the call graph) — repository + DB driver.

Nothing is mocked except the external Supabase driver (FakeSupabase). This is
the foundation the higher levels build on: prove the repository speaks to the
'database' correctly before wiring services and routers on top.
"""
import pytest

from app.repositories.learner_repository import LearnerRepository

pytestmark = pytest.mark.integration


def test_save_then_read_back(fake_supabase):
    fake_supabase(seed={"learners": []})
    repo = LearnerRepository()

    repo.save({"id": "l9", "name": "Zed"})

    assert repo.find_by_id("l9") == {"id": "l9", "name": "Zed"}
    assert [r["id"] for r in repo.list_all()] == ["l9"]
