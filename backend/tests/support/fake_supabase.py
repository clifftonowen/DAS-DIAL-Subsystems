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
eq, neq, gt, gte, lt, lte, like, ilike, in_, is_, not_, or_, order, limit, range,
single, execute.

MODELLED FOR REAL — these narrow, and a test can rely on them:
    eq, gt, ilike, in_, is_, or_, not_ (as a prefix to the next filter),
    order, limit, range, and `count=` on select.
PASS THROUGH — accepted but do NOT narrow:
    neq, gte, lt, lte, like.
Keep this split accurate. A filter that silently passes through makes every test of a
repository that relies on it pass whether or not the repository filters at all — extend
the class rather than leaving a lie here.

`neq` in particular does NOT narrow, so a delete filtered only by `neq` removes
everything, which happens to match how PostgREST's "delete every row" idiom behaves.

`upsert` honours `on_conflict`, which `LearnerRepository.upsert_many` depends on: the
merged `learners` table is keyed by a uuid the DIAL workbook has never heard of, so the
ingest conflicts on `student_id` instead. A double that guessed the key column would let
an ingest bug through — writing 5,783 duplicate rows instead of updating in place.

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
    """Mimics the object returned by `.execute()`.

    `.count` is None unless the query asked for one (`select(..., count="exact")`), matching
    PostgREST: the count comes from the Content-Range header, not the body.

    IT COUNTS THE FILTERED SET, BEFORE range/limit — which is what lets a repository ask for
    the total while transferring one row (`select(count="exact").limit(1)`). Counting after
    the slice would report the page size and every pager would say "1-24 of 24".
    """
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class _Query:
    """A chainable query/command builder bound to one table in the store."""

    def __init__(self, store, table, log=None, fail_on_execute=None):
        self._store = store
        self._table = table
        self._log = log if log is not None else []
        self._fail_on_execute = fail_on_execute
        self._op = "select"
        self._payload = None
        self._eq = []   # list of (col, value) equality filters
        self._gt = []   # list of (col, value) greater-than filters
        self._predicates = []   # arbitrary row -> bool, from ilike / in_ / is_ / or_
        self._order = []     # [(column, desc)] — applied left to right, as postgrest does
        self._range = None   # (start, end) — inclusive both ends, as PostgREST
        self._limit = None
        self._count = None       # the `count=` mode asked for, if any
        self._negate = False     # set by `.not_`, consumed by the next filter
        self._on_conflict = None

    # -- table switch (a couple of repos re-call .table() mid-chain) --
    def table(self, name):
        self._table = name
        return self

    # -- operations --
    def select(self, *_args, count=None, **_kw):
        """MIRRORS postgrest 0.16.11 — `count` only, deliberately NO `head`.

        `head=True` exists in newer postgrest and reads better, but `supabase==2.7.4` pins
        0.16.11, where it is a TypeError. This double once accepted it, so every unit test
        passed while every e2e run against the real driver died with

            select() got an unexpected keyword argument 'head'

        A double that is more permissive than the pinned library cannot catch that class of
        bug — it manufactures it. Keep this signature in step with the pin, and reject
        anything the pinned version would reject.
        """
        self._op = "select"
        self._count = count
        return self

    def insert(self, payload):
        self._op, self._payload = "insert", payload
        return self

    def upsert(self, payload, *, on_conflict="", **_kw):
        self._op, self._payload = "upsert", payload
        self._on_conflict = on_conflict or None
        return self

    def update(self, payload):
        self._op, self._payload = "update", payload
        return self

    def delete(self):
        self._op = "delete"
        return self

    # -- filters --
    def eq(self, col, val):
        return self._add(lambda r: r.get(col) == val)

    def gt(self, col, val):
        def hit(r):
            cell = r.get(col)
            return cell is not None and cell > val
        return self._add(hit)

    def ilike(self, col, pattern):
        """PostgREST's `*` wildcard, case-insensitive. Used by the learner search."""
        return self._add(lambda r: _ilike(r.get(col), pattern))

    def in_(self, col, values):
        return self._add(lambda r: r.get(col) in values)

    def is_(self, col, value):
        """`.is_(col, "null")` — PostgREST spells IS NULL with the string "null"."""
        want = None if value in (None, "null", "NULL") else value
        return self._add(lambda r: r.get(col) is want if want is None else r.get(col) == want)

    @property
    def not_(self):
        """A prefix, not a filter: `.not_.is_(col, "null")` negates the NEXT filter only.

        A property because that is how postgrest-py spells it — the chain reads
        `query.not_.is_(...)`, so this must return something with the filter methods on it.
        """
        self._negate = True
        return self

    def or_(self, filters, reference_table=None):
        """PostgREST's `or_("a.ilike.*x*,b.eq.1")` — comma-separated `col.op.value` terms.

        Modelled because the learner search is one `or_` across pseudonym, student_id and band.
        Left as a pass-through it would match every row, and a search test would pass against a
        repository that never filtered.
        """
        terms = [t for t in _split_top_level(filters) if t]
        return self._add(lambda r: any(_term_matches(r, t) for t in terms))

    def limit(self, size, **_kw):
        self._limit = size
        return self

    # Filters we accept but don't model precisely — they just return self. See the header.
    def neq(self, *_a, **_k): return self
    def gte(self, *_a, **_k): return self
    def lt(self, *_a, **_k): return self
    def lte(self, *_a, **_k): return self
    def like(self, *_a, **_k): return self

    def _add(self, predicate):
        """Register a predicate, applying and clearing any pending `.not_`."""
        if self._negate:
            self._negate = False
            self._predicates.append(lambda r: not predicate(r))
        else:
            self._predicates.append(predicate)
        return self

    # -- ordering + pagination --
    # These two ARE modelled, unlike the filters above, because a repository that pages
    # (LearnerScoreRepository.list_cohort — the cohort is ~5,800 rows against PostgREST's
    # 1,000-row cap) loops until a short page comes back. Against a passthrough `range`
    # every page is the full table, the loop never sees a short one, and the test hangs
    # instead of failing. A double that silently ignores paging cannot test paging.
    def order(self, column, desc=False, **_kw):
        # APPENDS, matching postgrest, which composes repeated order() calls into one
        # comma-separated clause. LearnerRepository.list_page relies on three keys
        # (caseload first, then name, then student id); a double that kept only the last
        # would silently test a different sort than production runs.
        self._order.append((column, desc))
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def single(self):
        self._single = True
        return self

    # -- terminal --
    def execute(self):
        # An opt-in driver failure: `fail_on_execute` lets an integration test put the
        # database out of reach from the bottom of the call graph. Off by default, so no
        # existing test is touched — the repositories reach the driver exactly here.
        if self._fail_on_execute is not None:
            raise self._fail_on_execute
        # Record every round trip so an integration test can assert that an edge
        # of the call graph was NOT taken (e.g. IT-6.4: no lookup on the
        # invalid-credentials path).
        self._log.append((self._table, self._op))
        rows = self._store.setdefault(self._table, [])
        if self._op == "select":
            out = [r for r in rows if self._matches(r)]
            # The count is of everything MATCHING THE FILTERS, before range/limit — that is what
            # PostgREST returns and what pagination needs ("showing 1-25 of 5,783").
            total = len(out) if self._count else None
            # Applied last key first, which is how you compose a multi-key sort out of stable
            # single-key ones — Python's sort is stable, so earlier keys survive later passes.
            for column, desc in reversed(self._order):
                out = sorted(out, key=lambda r: _sort_key(r.get(column)), reverse=desc)
            if self._range is not None:
                start, end = self._range
                out = out[start:end + 1]        # PostgREST's range is inclusive at both ends
            if self._limit is not None:
                out = out[:self._limit]
            return _Result(out, count=total)
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
                # Which column(s) the upsert conflicts on differs by call. `on_conflict` is
                # explicit and wins; otherwise fall back to the primary key `id`. A comma-
                # separated value is a COMPOSITE key, as PostgREST spells it.
                #
                # Both of those matter for real bugs. `learners` is keyed by a uuid the DIAL
                # workbook has never heard of, so the ingest conflicts on `student_id`; and
                # `learner_sittings` conflicts on (learner_id, semester), because a learner sits
                # a given semester once. Guessing either would let a re-ingest append duplicates
                # instead of updating in place — thousands of rows, no error.
                key_columns = [c.strip() for c in (self._on_conflict or "id").split(",")]
                key = tuple(item.get(c) for c in key_columns)
                existing = (
                    None if any(part is None for part in key)
                    else next(
                        (r for r in rows
                         if tuple(r.get(c) for c in key_columns) == key), None
                    )
                )
                if existing is None:
                    rows.append(dict(item))
                else:
                    # A partial payload updates only the columns it carries — which is what lets
                    # the ingest refresh a cohort learner's marks without touching the pseudonym
                    # and on_caseload flag it does not send.
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
        return all(predicate(row) for predicate in self._predicates)


# ── sorting ──────────────────────────────────────────────────────────────────
def _sort_key(value):
    """A total order over a column that may hold anything, including None.

    Sorts are per column, but a column can be a bool (`on_caseload`), a string (`pseudonym`) or
    NULL for some rows, and Python raises on `str < bool`. The type tag keeps unlike values from
    ever being compared to each other, and Nones sort last as Postgres does by default.

    Booleans are tagged with numbers deliberately: Postgres orders false before true, and
    `.order("on_caseload", desc=True)` has to put the caseload first.
    """
    if value is None:
        return (3, 0.0, "")
    if isinstance(value, bool):
        return (0, float(value), "")
    if isinstance(value, (int, float)):
        return (0, float(value), "")
    return (1, 0.0, str(value))


# ── filter helpers ───────────────────────────────────────────────────────────
def _ilike(cell, pattern):
    """PostgREST's ilike: `*` is the wildcard (not SQL's `%`), matching is case-insensitive."""
    if cell is None:
        return False
    text = str(cell).lower()
    body = str(pattern).lower().replace("%", "*")
    if "*" not in body:
        return text == body
    # Anchor unless the pattern opens/closes with a wildcard, then match the parts in order.
    parts = body.split("*")
    if parts[0] and not text.startswith(parts[0]):
        return False
    if parts[-1] and not text.endswith(parts[-1]):
        return False
    cursor = len(parts[0])
    for part in parts[1:-1]:
        if not part:
            continue
        found = text.find(part, cursor)
        if found == -1:
            return False
        cursor = found + len(part)
    return True


def _split_top_level(filters):
    """Split an or_() string on commas that are not inside parentheses.

    `in.(a,b)` values carry their own commas, so a naive split would tear a term in half.
    """
    terms, depth, current = [], 0, []
    for char in str(filters):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if char == "," and depth == 0:
            terms.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    terms.append("".join(current).strip())
    return terms


def _term_matches(row, term):
    """One `col.op.value` term from an or_() string."""
    parts = term.split(".", 2)
    if len(parts) < 3:
        return False
    column, op, value = parts
    cell = row.get(column)
    if op == "ilike":
        return _ilike(cell, value)
    if op == "like":
        return _ilike(cell, value)      # close enough; the double does not model case
    if op == "eq":
        return str(cell) == value
    if op == "is":
        return cell is None if value in ("null", "NULL") else str(cell) == value
    # An unmodelled operator must not silently match everything — that is how a broken filter
    # passes its test. Fail the term instead, so the test goes red and names the gap.
    raise NotImplementedError(f"fake_supabase: or_() operator {op!r} is not modelled")


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
        fail_on_execute: when set, every `.execute()` raises this exception —
            an opt-in way to model an unreachable database from the driver seam.
    """

    def __init__(self, seed=None, user_id="test-therapist-id",
                 auth_users=None, confirm_email=False, fail_on_execute=None):
        # Deep-ish copy so tests don't leak state between cases.
        self.store = {k: [dict(r) for r in v] for k, v in (seed or {}).items()}
        self.auth = _Auth(user_id, auth_users=auth_users, confirm_email=confirm_email)
        # Every executed round trip, as (table, op) — lets a test prove an edge
        # was never taken. See `queries_on()`.
        self.queries = []
        self._fail_on_execute = fail_on_execute

    def table(self, name):
        return _Query(self.store, name, log=self.queries,
                      fail_on_execute=self._fail_on_execute)

    def queries_on(self, table):
        """The round trips made against one table, for interaction assertions."""
        return [q for q in self.queries if q[0] == table]
