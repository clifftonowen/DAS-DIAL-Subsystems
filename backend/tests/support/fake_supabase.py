"""In-memory Supabase double for hermetic unit + integration tests.

The real repositories reach the database through a single seam:
`app.core.supabase_client.get_supabase()` -> a Supabase client, used as

    client.table("learners").select("*").eq("id", x).execute().data

`FakeSupabase` implements just enough of that fluent PostgREST-style chain
(backed by plain dicts) plus the `.auth` surface used by
`app.core.security.current_therapist`. Swap it in with the `fake_supabase`
fixture in conftest.py — no network, no real project required.

Supported chain methods: table, select, insert, upsert, update, delete,
eq, neq, gt, gte, lt, lte, order, limit, range, single, execute.
Unsupported filters simply pass through (they don't narrow results), which
keeps the double small; extend here if a repository needs more precision.
"""
from types import SimpleNamespace


class _Result:
    """Mimics the object returned by `.execute()` — only `.data` is used."""
    def __init__(self, data):
        self.data = data


class _Query:
    """A chainable query/command builder bound to one table in the store."""

    def __init__(self, store, table):
        self._store = store
        self._table = table
        self._op = "select"
        self._payload = None
        self._eq = []   # list of (col, value) equality filters
        self._gt = []   # list of (col, value) greater-than filters

    # -- table switch (a couple of repos re-call .table() mid-chain) --
    def table(self, name):
        self._table = name
        return self

    # -- operations --
    def select(self, *_args, **_kw):
        self._op = "select"
        return self

    def insert(self, payload):
        self._op, self._payload = "insert", payload
        return self

    def upsert(self, payload, **_kw):
        self._op, self._payload = "upsert", payload
        return self

    def update(self, payload):
        self._op, self._payload = "update", payload
        return self

    def delete(self):
        self._op = "delete"
        return self

    # -- filters --
    def eq(self, col, val):
        self._eq.append((col, val))
        return self

    def gt(self, col, val):
        self._gt.append((col, val))
        return self

    # Filters we accept but don't model precisely — they just return self.
    def neq(self, *_a, **_k): return self
    def gte(self, *_a, **_k): return self
    def lt(self, *_a, **_k): return self
    def lte(self, *_a, **_k): return self
    def like(self, *_a, **_k): return self
    def ilike(self, *_a, **_k): return self
    def in_(self, *_a, **_k): return self
    def order(self, *_a, **_k): return self
    def limit(self, *_a, **_k): return self
    def range(self, *_a, **_k): return self

    def single(self):
        self._single = True
        return self

    # -- terminal --
    def execute(self):
        rows = self._store.setdefault(self._table, [])
        if self._op == "select":
            out = [r for r in rows if self._matches(r)]
            return _Result(out)
        if self._op in ("insert", "upsert"):
            items = self._payload if isinstance(self._payload, list) else [self._payload]
            rows.extend(items)
            return _Result(items)
        if self._op == "update":
            changed = []
            for r in rows:
                if self._matches(r):
                    r.update(self._payload)
                    changed.append(r)
            return _Result(changed)
        if self._op == "delete":
            keep, removed = [], []
            for r in rows:
                (removed if self._matches(r) else keep).append(r)
            self._store[self._table] = keep
            return _Result(removed)
        return _Result([])

    def _matches(self, row):
        for col, val in self._eq:
            if row.get(col) != val:
                return False
        for col, val in self._gt:
            cell = row.get(col)
            if cell is None or not cell > val:
                return False
        return True


class _Auth:
    """Minimal `.auth` surface used by security.current_therapist."""

    def __init__(self, user_id):
        self._user_id = user_id

    def get_user(self, _token):
        # current_therapist reads result.user.id
        return SimpleNamespace(user=SimpleNamespace(id=self._user_id))


class FakeSupabase:
    """Drop-in stand-in for the Supabase client.

    Args:
        seed: optional {table_name: [row_dicts]} to preload.
        user_id: the auth user id returned by `.auth.get_user()`.
    """

    def __init__(self, seed=None, user_id="test-therapist-id"):
        # Deep-ish copy so tests don't leak state between cases.
        self.store = {k: [dict(r) for r in v] for k, v in (seed or {}).items()}
        self.auth = _Auth(user_id)

    def table(self, name):
        return _Query(self.store, name)
