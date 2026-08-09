"""UNIT — LearnerService business logic in isolation.

The repository collaborator is a Mock, so this test exercises ONLY the
service's own logic (the 404 rule in `get_learner`) — the defining trait of a
unit test at this activation bar.
"""
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from app.services.learner_service import LearnerService

pytestmark = pytest.mark.unit


def test_get_learner_returns_row_when_found():
    svc = LearnerService()
    svc.learners = Mock()
    svc.learners.find_by_id.return_value = {"id": "l1", "name": "Ada"}

    assert svc.get_learner("l1") == {"id": "l1", "name": "Ada"}
    svc.learners.find_by_id.assert_called_once_with("l1")


def test_get_learner_raises_404_when_missing():
    svc = LearnerService()
    svc.learners = Mock()
    svc.learners.find_by_id.return_value = None

    with pytest.raises(HTTPException) as exc:
        svc.get_learner("nope")
    assert exc.value.status_code == 404


def test_list_learners_asks_for_one_page():
    svc = LearnerService()
    svc.learners = Mock()
    svc.learners.list_page.return_value = ([{"id": "l1", "pseudonym": "Ada"}], 137)

    page = svc.list_learners(page=3, per_page=10, query="ada")

    assert [i.id for i in page.items] == ["l1"]
    assert page.total == 137, "the total is the filtered set, so the pager can size itself"
    svc.learners.list_page.assert_called_once_with(
        limit=10, offset=20, query="ada", caseload_only=True)


def test_list_learners_defaults_to_the_caseload():
    """The Learners tab is where a therapist works with their OWN learners.

    Defaulting to the whole table would open it on thousands of anonymised research rows with
    the ten that matter somewhere on page 200.
    """
    svc = LearnerService()
    svc.learners = Mock()
    svc.learners.list_page.return_value = ([], 0)

    svc.list_learners()

    assert svc.learners.list_page.call_args.kwargs["caseload_only"] is True


def test_per_page_is_clamped_not_trusted():
    """It arrives from the query string.

    Unbounded, a caller could ask for the entire table in one request — the exact read the
    paging exists to prevent — and PostgREST would truncate it at 1,000 without saying so.
    """
    svc = LearnerService()
    svc.learners = Mock()
    svc.learners.list_page.return_value = ([], 0)

    svc.list_learners(per_page=100_000)

    assert svc.learners.list_page.call_args.kwargs["limit"] == 100


def test_a_page_below_one_is_clamped():
    """`offset` must never go negative — PostgREST rejects the range outright."""
    svc = LearnerService()
    svc.learners = Mock()
    svc.learners.list_page.return_value = ([], 0)

    svc.list_learners(page=0)

    assert svc.learners.list_page.call_args.kwargs["offset"] == 0
