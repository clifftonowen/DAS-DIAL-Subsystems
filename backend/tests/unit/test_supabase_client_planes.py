"""UNIT — the data-plane / auth-plane Supabase client split.

Regression cover for a bug that took down every login. `sign_in_with_password`
and `sign_up` emit a SIGNED_IN event, and supabase-py reacts by discarding the
client's PostgREST instance and REPLACING its Authorization header with that
user's access token (supabase/_sync/client.py::_listen_to_auth_events).

`get_supabase()` is an lru_cache singleton, so while AuthGateway shared it with
every repository, one login silently demoted the whole process from service-role
to "whoever logged in most recently". The immediate symptom was PostgREST 42501
("new row violates row-level security policy") on the `users` upsert; the wider
one is that one therapist's login changes the privileges another therapist's
request runs under.

These assertions are structural on purpose: FakeSupabase cannot reproduce the
header swap, so no functional test at any tier would catch a regression here.
"""
import pytest

import app.core.supabase_client as sc
import app.gateways.auth_gateway as auth_gateway

pytestmark = pytest.mark.unit


def test_auth_gateway_never_touches_the_data_plane_client():
    """AuthGateway must bind the auth-plane factory, and only that one."""
    assert hasattr(auth_gateway, "get_auth_supabase")
    assert not hasattr(auth_gateway, "get_supabase"), (
        "AuthGateway imported the DATA-plane client; a sign-in on it would rewrite "
        "the service-role Authorization header every repository depends on"
    )


def test_the_two_factories_return_different_clients(monkeypatch):
    """Separate lru_cache entries, so a SIGNED_IN event on one cannot reach the other."""
    import supabase

    monkeypatch.setattr(sc.settings, "supabase_url", "https://example.supabase.co")
    monkeypatch.setattr(sc.settings, "supabase_key", "test-service-role-key")
    monkeypatch.setattr(supabase, "create_client", lambda _url, _key: object())

    sc.get_supabase.cache_clear()
    sc.get_auth_supabase.cache_clear()
    try:
        data_client = sc.get_supabase()
        auth_client = sc.get_auth_supabase()

        assert data_client is not auth_client
        assert data_client is sc.get_supabase()        # still cached per plane
        assert auth_client is sc.get_auth_supabase()
    finally:
        # Don't leave stub clients cached for later tests.
        sc.get_supabase.cache_clear()
        sc.get_auth_supabase.cache_clear()
