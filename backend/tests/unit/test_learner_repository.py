"""UNIT — LearnerRepository in isolation.

One "activation bar": a single repository method, with the database driver
replaced by the in-memory FakeSupabase. No service, no router, no network.
"""
import pytest

from app.repositories.learner_repository import LearnerRepository

pytestmark = pytest.mark.unit


def test_find_by_id_returns_matching_row(fake_supabase):
    fake_supabase(seed={"learners": [
        {"id": "l1", "name": "Ada"},
        {"id": "l2", "name": "Bo"},
    ]})
    repo = LearnerRepository()

    assert repo.find_by_id("l1") == {"id": "l1", "name": "Ada"}


def test_find_by_id_returns_none_when_absent(fake_supabase):
    fake_supabase(seed={"learners": []})
    repo = LearnerRepository()

    assert repo.find_by_id("missing") is None


def test_list_all_returns_every_row(fake_supabase):
    fake_supabase(seed={"learners": [{"id": "l1"}, {"id": "l2"}]})
    repo = LearnerRepository()

    assert [r["id"] for r in repo.list_all()] == ["l1", "l2"]
