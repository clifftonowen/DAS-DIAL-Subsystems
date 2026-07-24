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


def test_list_learners_delegates_to_repository():
    svc = LearnerService()
    svc.learners = Mock()
    svc.learners.list_all.return_value = [{"id": "l1"}]

    assert svc.list_learners() == [{"id": "l1"}]
    svc.learners.list_all.assert_called_once_with()
