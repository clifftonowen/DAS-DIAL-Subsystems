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

    repo.save({"id": "l9", "pseudonym": "Zed", "on_caseload": True})

    assert repo.find_by_id("l9")["pseudonym"] == "Zed"
    # list_page, not list_all: `learners` holds the whole DAS cohort as well as the caseload,
    # and PostgREST truncates an unpaged select at 1,000 rows without erroring.
    rows, total = repo.list_page(limit=10, offset=0)
    assert [r["id"] for r in rows] == ["l9"]
    assert total == 1
