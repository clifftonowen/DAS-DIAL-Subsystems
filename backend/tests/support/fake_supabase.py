"""In-memory Supabase double for hermetic unit + integration tests.

The real repositories reach the database through a single seam:
`app.core.supabase_client.get_supabase()` -> a Supabase client, used as

    client.table("learners").select("*").eq("id", x).execute().data

`FakeSupabase` implements just enough of that fluent PostgREST-style chain
(backed by plain dicts) plus the `.auth` surface used by
`app.core.security.current_therapist` and `app.gateways.auth_gateway`. Swap it in
with the `fake_supabase` fixture in conftest.py -- no network, no real project
required.

Supported chain methods: table, select, insert, upsert, update, delete,
eq, neq, gt, gte, lt, lte, order, limit, range, single, execute.
`eq`, `gt`, `order` and `range` are modelled for real; the remaining filters pass
through (they don't narrow results), which keeps the double small — extend here if a
repository needs more precision. `neq` in particular does NOT narrow, so a delete
filtered only by `neq` removes everything, which happens to match how PostgREST's
"delete every row" idiom behaves.

Supported auth methods (UC6 Log In / UC8 Sign Up): sign_up,
sign_in_with_password, get_user, admin.sign_out, admin.delete_user. Failures raise
the *real* gotrue exception classes, matching which type live Supabase raises for
each case, because `AuthGateway` discriminates on them -- a bare `Exception` would
sail straight through it.
"""
import time
from types import SimpleNamespace
from uuid import uuid4

try:  # same guarded import as app.gateways.auth_gateway
    # The double raises the SAME classes real Supabase does. That matters: a weak
    # password surfaces as AuthWeakPasswordError, which is NOT an AuthApiError, and
    # a fake that raised the wrong type would hide exactly that bug.
    from gotrue.errors import AuthApiError, AuthWeakPasswordError
except Exception:  # pragma: no cover - fallback if the package layout changes
    class AuthApiError(Exception):
        def __init__(self, message, status=400, code=None):
            super().__init__(message)
            self.status, self.code = status, code

    class AuthWeakPasswordError(Exception):
        def __init__(self, message, status=422, reasons=None):
            super().__init__(message)
            self.status, self.reasons = status, reasons or []


class _Result:
    """Mimics the object returned by `.execute()` — only `.data` is used."""
    def __init__(self, data):
        self.data = data


class _Query:
    """A chainable query/command builder bound to one table in the store."""

    def __init__(self, store, table, log=None):
        self._store = store
        self._table = table
        self._log = log if log is not None else []
        self._op = "select"
        self._payload = None
        self._eq = []   # list of (col, value) equality filters
        self._gt = []   # list of (col, value) greater-than filters
        self._order = None   # (column, desc)
        self._range = None   # (start, end) — inclusive both ends, as PostgREST

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
    def limit(self, *_a, **_k): return self

    # -- ordering + pagination --
    # These two ARE modelled, unlike the filters above, because a repository that pages
    # (LearnerScoreRepository.list_cohort — the cohort is ~5,800 rows against PostgREST's
    # 1,000-row cap) loops until a short page comes back. Against a passthrough `range`
    # every page is the full table, the loop never sees a short one, and the test hangs
    # instead of failing. A double that silently ignores paging cannot test paging.
    def order(self, column, desc=False, **_kw):
        self._order = (column, desc)
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def single(self):
        self._single = True
        return self

    # -- terminal --
    def execute(self):
        # Record every round trip so an integration test can assert that an edge
        # of the call graph was NOT taken (e.g. IT-6.4: no lookup on the
        # invalid-credentials path).
        self._log.append((self._table, self._op))
        rows = self._store.setdefault(self._table, [])
        if self._op == "select":
            out = [r for r in rows if self._matches(r)]
            if self._order is not None:
                column, desc = self._order
                # `""` as the sort key for a missing/None cell: real Postgres would order
                # nulls, and comparing None against a str raises in Python.
                out = sorted(out, key=lambda r: (r.get(column) is None, r.get(column) or ""),
                             reverse=desc)
            if self._range is not None:
                start, end = self._range
                out = out[start:end + 1]        # PostgREST's range is inclusive at both ends
            return _Result(out)
        if self._op == "insert":
            items = self._payload if isinstance(self._payload, list) else [self._payload]
            rows.extend(dict(i) for i in items)
            return _Result(items)
        if self._op == "upsert":
            # Real upsert conflicts on the primary key, so saving the same row
            # twice must leave ONE row. Without this, UserRepository.save being
            # idempotent is untestable.
            items = self._payload if isinstance(self._payload, list) else [self._payload]
            for item in items:
                # Which column is the primary key differs by table: most use `id`, but
                # learner_scores is keyed by the anonymised `student_id`. Without this the
                # cohort upsert would append 5,783 duplicate rows on every re-ingest instead
                # of conflicting, and the double would not catch it.
                key_column = next((c for c in ("id", "student_id") if c in item), None)
                key = item.get(key_column) if key_column else None
                existing = next(
                    (r for r in rows if key is not None and r.get(key_column) == key), None
                )
                if existing is None:
                    rows.append(dict(item))
                else:
                    existing.update(item)
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


class _AuthAdmin:
    """The `.auth.admin` surface — service-role operations."""

    def __init__(self, auth):
        self._auth = auth

    def sign_out(self, access_token):
        """Revoke a token. Revoking an unknown/expired token is an error, which
        is exactly the case AuthService treats as idempotent."""
        if self._auth._tokens.pop(access_token, None) is None:
            raise AuthApiError("Invalid token", 401, "invalid_token")

    def delete_user(self, user_id):
        for email, user in list(self._auth._users.items()):
            if user["id"] == user_id:
                del self._auth._users[email]
                return
        raise AuthApiError("User not found", 404, "user_not_found")


class _Auth:
    """The `.auth` surface used by AuthGateway and security.current_therapist.

    Holds its own little user directory so a sign-up followed by a log-in behaves
    like the real thing across a whole integration test.
    """

    def __init__(self, user_id, auth_users=None, confirm_email=False):
        self._default_user_id = user_id
        self._confirm_email = confirm_email
        self._users = {}    # email -> {"id", "email", "password"}
        self._tokens = {}   # access_token -> user id
        for u in auth_users or []:
            self._users[u["email"]] = {
                "id": u.get("id") or str(uuid4()),
                "email": u["email"],
                "password": u["password"],
            }
        self.admin = _AuthAdmin(self)

    # ---------------------------------------------------------------- UC8
    MIN_PASSWORD_LENGTH = 6   # Supabase's own default

    def sign_up(self, credentials):
        email, password = credentials["email"], credentials["password"]
        if len(password) < self.MIN_PASSWORD_LENGTH:
            raise AuthWeakPasswordError(
                f"Password should be at least {self.MIN_PASSWORD_LENGTH} characters.",
                422, ["length"],
            )
        if email in self._users:
            raise AuthApiError("User already registered", 422, "user_already_exists")
        user = {"id": str(uuid4()), "email": email, "password": password}
        self._users[email] = user
        # With email confirmation on, Supabase returns a user but no session.
        session = None if self._confirm_email else self._issue(user)
        return SimpleNamespace(user=self._as_user(user), session=session)

    # ---------------------------------------------------------------- UC6
    def sign_in_with_password(self, credentials):
        email, password = credentials["email"], credentials["password"]
        user = self._users.get(email)
        if user is None or user["password"] != password:
            raise AuthApiError("Invalid login credentials", 400, "invalid_credentials")
        return SimpleNamespace(user=self._as_user(user), session=self._issue(user))

    def get_user(self, access_token):
        """Resolve a bearer token, as current_therapist does on every protected
        request. Tokens this double issued map to their own user; anything else
        falls back to the fixture's `user_id` so tests written before the auth
        surface existed keep working."""
        user_id = self._tokens.get(access_token, self._default_user_id)
        if user_id is None:
            return None
        return SimpleNamespace(user=SimpleNamespace(id=user_id))

    # -- helpers --
    def _issue(self, user):
        token = f"fake-access-{uuid4().hex[:12]}"
        self._tokens[token] = user["id"]
        return SimpleNamespace(
            access_token=token,
            refresh_token=f"fake-refresh-{uuid4().hex[:12]}",
            expires_at=int(time.time()) + 3600,
        )

    @staticmethod
    def _as_user(user):
        return SimpleNamespace(id=user["id"], email=user["email"])


class FakeSupabase:
    """Drop-in stand-in for the Supabase client.

    Args:
        seed: optional {table_name: [row_dicts]} to preload.
        user_id: the auth user id `.auth.get_user()` falls back to.
        auth_users: optional [{"id"?, "email", "password"}] credential pairs the
            fake Authentication Service accepts.
        confirm_email: when True, `sign_up` returns a user with no session,
            modelling a project that has email confirmation enabled.
    """

    def __init__(self, seed=None, user_id="test-therapist-id",
                 auth_users=None, confirm_email=False):
        # Deep-ish copy so tests don't leak state between cases.
        self.store = {k: [dict(r) for r in v] for k, v in (seed or {}).items()}
        self.auth = _Auth(user_id, auth_users=auth_users, confirm_email=confirm_email)
        # Every executed round trip, as (table, op) — lets a test prove an edge
        # was never taken. See `queries_on()`.
        self.queries = []

    def table(self, name):
        return _Query(self.store, name, log=self.queries)

    def queries_on(self, table):
        """The round trips made against one table, for interaction assertions."""
        return [q for q in self.queries if q[0] == table]
