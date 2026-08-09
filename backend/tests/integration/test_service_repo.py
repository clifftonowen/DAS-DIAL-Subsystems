"""INTEGRATION level 2 — service + real repository together.

Moving one step up the call graph: a REAL LearnerService driving a REAL
LearnerRepository. Nothing between the layers is mocked — only the Supabase
driver underneath. Catches wiring bugs a unit test (which mocks the repo)
cannot.
"""
import pytest
from fastapi import HTTPException

from app.services.learner_service import LearnerService

pytestmark = pytest.mark.integration


def test_get_learner_reads_through_real_repository(fake_supabase):
    fake_supabase(seed={"learners": [{"id": "l1", "name": "Ada"}]})
    svc = LearnerService()  # constructs a real LearnerRepository internally

    assert svc.get_learner("l1")["name"] == "Ada"


def test_get_learner_404_flows_from_empty_db(fake_supabase):
    fake_supabase(seed={"learners": []})
    svc = LearnerService()

    with pytest.raises(HTTPException) as exc:
        svc.get_learner("l1")
    assert exc.value.status_code == 404
