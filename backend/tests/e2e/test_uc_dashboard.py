"""E2E use case: "Therapist opens the dashboard".

Exercises the dashboard endpoints against the real project. These endpoints
have built-in fallbacks (see routers/dashboard.py), so they return a valid
shape even on a sparsely-seeded test project — which keeps this use case
stable while still proving auth + routing + the live stack end to end.
"""
import pytest

pytestmark = pytest.mark.e2e


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_dashboard_stats_shape(client, access_token):
    resp = client.get("/dashboard/stats", headers=_auth(access_token))

    assert resp.status_code == 200
    body = resp.json()
    assert {"flagged", "needs_profiling", "high_risk", "inactive"} <= body.keys()


def test_dashboard_tasks_and_events_are_lists(client, access_token):
    tasks = client.get("/dashboard/tasks", headers=_auth(access_token))
    events = client.get("/dashboard/events", headers=_auth(access_token))

    assert tasks.status_code == 200 and isinstance(tasks.json(), list)
    assert events.status_code == 200 and isinstance(events.json(), list)
