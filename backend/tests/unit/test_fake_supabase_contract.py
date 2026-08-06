"""UNIT — the in-memory double must not be more permissive than the real driver.

    AB2.27  tests.support.fake_supabase — API contract   UT-2.73

WHY THIS FILE EXISTS. Every other test in this suite runs against `FakeSupabase`, a hand-written
stand-in. A double that ACCEPTS MORE than the real library does not merely fail to catch bugs —
it manufactures them: the code under test is written to an API that does not exist, every unit
and integration test passes, and the failure surfaces only in e2e, against the live project.

That happened. `LearnerRepository.count()` was written as

    select("id", count="exact", head=True)

which is valid in postgrest 2.x but a TypeError in 0.16.11 — the version `supabase==2.7.4`
pins and CI installs. The double accepted `head`, so 195 tests passed and every e2e run died
with `select() got an unexpected keyword argument 'head'`.

These tests introspect the postgrest that is ACTUALLY INSTALLED and compare it against the
double, so the mismatch fails here — hermetically, in the cheapest tier — rather than in e2e.

WHAT THEY CANNOT DO. They compare against the installed version, not the pinned one, so a
developer whose venv has drifted AHEAD of `requirements.txt` still sees them pass — `head=` is
not a bug against postgrest 2.x, it is only a bug against the 0.16.11 CI installs. Verified
both ways: with `head=` reintroduced into the double, the first test fails under 0.16.11 and
passes under 2.31.0. So this catches the mistake in CI, which is where it counts, but the
durable fix is a local environment that matches the pin.
"""
import inspect

import pytest

from tests.support.fake_supabase import FakeSupabase

postgrest = pytest.importorskip("postgrest", reason="postgrest ships with supabase, a runtime dep")

from postgrest._sync.request_builder import (  # noqa: E402
    SyncRequestBuilder,
    SyncSelectRequestBuilder,
)

pytestmark = pytest.mark.unit


def _kwargs(func) -> set[str]:
    """The KEYWORD-ONLY arguments a callable accepts, ignoring **kwargs catch-alls.

    Keyword-only is the right comparison: those are the names a caller writes out
    (`count=`, `on_conflict=`, and the `head=` that started this), so a mismatch there is a
    TypeError at runtime. Positional parameters are compared by position, not name — the double
    calls its payload `payload` where postgrest calls it `json`, which is invisible to callers
    and not a contract difference.
    """
    return {
        name for name, p in inspect.signature(func).parameters.items()
        if p.kind is p.KEYWORD_ONLY
    }


def _query():
    return FakeSupabase().table("learners")


def test_the_double_accepts_no_select_kwarg_the_real_driver_rejects():
    """UT-2.73: THE REGRESSION. `head=True` is the one that got through.

    Compared against the INSTALLED postgrest rather than a hardcoded list, so this tracks the
    pin: bump `supabase` and the double is free to grow whatever the new version allows.
    """
    real = _kwargs(SyncRequestBuilder.select)
    fake = _kwargs(FakeSupabase().table("learners").select)

    extra = fake - real
    assert not extra, (
        f"the double accepts {sorted(extra)} on select() but postgrest "
        f"{postgrest.__version__} does not — code written against it dies only in e2e"
    )


def test_the_double_accepts_no_upsert_kwarg_the_real_driver_rejects():
    """UT-2.73: the ingest's `on_conflict` goes through here, on two different keys."""
    extra = _kwargs(FakeSupabase().table("learners").upsert) - _kwargs(SyncRequestBuilder.upsert)

    assert not extra, f"the double accepts {sorted(extra)} on upsert(), postgrest does not"


@pytest.mark.parametrize("method", [
    "eq", "neq", "gt", "gte", "lt", "lte", "like", "ilike", "in_", "is_", "or_",
    "order", "limit", "range",
])
def test_every_chain_method_the_double_models_exists_on_the_real_builder(method):
    """UT-2.73: the reverse direction — the double must not invent methods either.

    A repository calling a method only the double has would fail the same way: green locally,
    AttributeError against the real project.
    """
    assert hasattr(SyncSelectRequestBuilder, method), (
        f"the double models .{method}(), which postgrest {postgrest.__version__} lacks"
    )


def test_not_is_a_property_on_both():
    """UT-2.73: `.not_.is_(col, "null")` — a prefix, not a call.

    Modelled as a property in the double because that is how postgrest spells it; were it a
    method in one and a property in the other, the chain would break at runtime only.
    """
    assert isinstance(
        inspect.getattr_static(SyncSelectRequestBuilder, "not_"), property
    )
    assert isinstance(inspect.getattr_static(type(_query()), "not_"), property)


def test_count_reaches_the_result_without_head():
    """UT-2.73: the shape `count()` now relies on.

    `count="exact"` + `.limit(1)` is how a total is fetched on the pinned version. PostgREST
    counts the whole filtered set and the limit only trims the body, so the double must report
    the total, not the page size — or every pager would read "1-24 of 24".
    """
    fake = FakeSupabase(seed={"learners": [{"id": f"l{i}"} for i in range(70)]})

    result = fake.table("learners").select("id", count="exact").limit(1).execute()

    assert result.count == 70, "the count is of the filtered set, before the limit"
    assert len(result.data) == 1, "the limit still trims the body"
