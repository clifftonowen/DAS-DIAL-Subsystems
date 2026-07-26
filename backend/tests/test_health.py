"""UNIT — /health liveness probe.

Marked `unit` so `pytest -m unit` (all CI ever runs) actually collects it;
unmarked, this file was never executed by any job.
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app

pytestmark = pytest.mark.unit


def test_health():
    r = TestClient(app).get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
