# Frontend integration tests (Jest + MSW)

**Status: implemented**, and running in CI as its own `frontend-integration` job
(`npm run test:integration`).

| File | Covers |
|---|---|
| `AuthView.uc6.integration.test.jsx` | UC6 log in — IT-6.9, IT-6.10 |
| `AuthView.uc8.integration.test.jsx` | UC8 sign up — IT-8.8, IT-8.9 |
| `UC4Review.integration.test.jsx` | UC4 review + approval — IT-4.6, IT-4.7 |
| `LearnersPage.integration.test.jsx` | UC9 list, search, navigation, error, caseload toggle |
| `LearnerDetailPage.uc3.integration.test.jsx` | UC3 generate — IT-3.11 to IT-3.14 |
| `ShareWindow.uc7.integration.test.jsx` | UC7 share — IT-7.12 to IT-7.15 |

**Two live bugs this tier has already caught**, both invisible to the unit tests because those
mock `lib/api.js` and so cannot see what crosses the wire:

- `LearnerDetailPage` gated its activity re-fetch on `status === "GENERATED"`, which the backend
  stopped sending when UC3 gained its validate loop. A successful generation rendered nothing.
- `api.js` threw a bare `Error` with no `status`, so `ShareWindow`'s "is this retriable?" check
  was always true and its terminal-failure branch was unreachable.

Both are the same shape: a **contract between the client and the server** that no other tier
looks at. That is what this tier is for — prefer adding cases here that assert request shaping
and response handling, not rendering detail a unit test covers more cheaply.

## What these are

Integration tests render a **whole view (or a subtree of components) with routing real** and only
the **network** mocked. They sit between:

- **unit** (`src/components/__tests__/`, `src/views/__tests__/`) — one component, every
  collaborator mocked at the module boundary, and
- **system** (`backend/tests/system/`, Selenium) — the real browser against the real backend.

They run in Jest/jsdom, so they're fast and deterministic (no browser, no live backend), and they
catch things unit tests can't: data-fetching + rendering + filtering + navigation working together.

For UC6/UC8 this is **level 4** of the bottom-up call graph — the
`AuthView -> AuthController` message across the HTTP boundary. It is the only level where
`src/lib/api.js` is *real code under test*, which matters because that is where request
shaping and error handling live. Levels 1–3 are in `backend/tests/integration/`.

## The tool: MSW (Mock Service Worker)

Instead of mocking `lib/api.js` function-by-function, MSW intercepts the real `fetch` calls the app
makes and returns canned JSON. That means the component under test runs its **actual** data path.

`msw` is installed. Shared setup lives in `src/test-utils/`:

- `handlers.js` — default handlers for routes several tests share, matched with `*` wildcards
- `server.js` — `setupServer(...handlers)`

Lifecycle hooks belong in each test file, so unit tests never start a server:

```js
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
```

`onUnhandledRequest: "error"` is deliberate — it turns "the app never made the request" into a
loud failure instead of a silent pass.

## Writing a test

```jsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { server } from "../../test-utils/server";
import AuthView from "../AuthView";

// createClient runs at import time, so lib/supabase is still mocked — it's the
// token *store*, not the thing under test.
jest.mock("../../lib/supabase", () => ({
  supabase: {
    auth: {
      setSession: jest.fn(),
      getSession: async () => ({ data: { session: null } }),
    },
  },
}));

test("issues the request and stores the session", async () => {
  let received;
  server.use(http.post("*/auth/login", async ({ request }) => {
    received = await request.json();                       // assert the body that went out
    return HttpResponse.json({ access_token: "t", refresh_token: "r" });
  }));
  render(<AuthView />);
  // …fill and submit…
  expect(received).toEqual({ email: "…", password: "…" });
});
```

Notes:
- Wrap in `MemoryRouter` for views that use `useNavigate` / `<Link>`. `AuthView` doesn't —
  `main.jsx` swaps it for `<Dashboard>` on `onAuthStateChange`, and `Dashboard` owns the router.
- Use `findBy*` / `waitFor` for anything that appears after the fetch resolves.
- Under Jest `process.env.VITE_API_URL` is unset, so `api.js` falls back to
  `http://localhost:8000`. The `*` wildcards mean handlers match regardless.

## Jest configuration this tier depends on

Three things in `jest.config.cjs` exist for MSW; changing them will break these tests:

1. **`testEnvironment: "jest-fixed-jsdom"`** — plain `jsdom` deletes Node's `fetch`,
   `Request`/`Response`, streams and `BroadcastChannel`. MSW v2 needs them. This is a thin
   wrapper that keeps them; everything else behaves like jsdom. (Polyfilling by hand with
   `undici` was tried first and is a losing game — it wants an ever-growing list of globals.)
2. **`transformIgnorePatterns`** — MSW and a few of its deps (`rettime`, `until-async`,
   `@open-draft/*`) ship ESM only, and Jest skips `node_modules` when transforming. Only those
   packages are whitelisted, so the rest of `node_modules` stays untransformed and fast.
3. **`test/babelPluginImportMeta.cjs`** — rewrites Vite's `import.meta.env` so Jest can load
   `src/lib/api.js` and `src/lib/supabase.js` at all. The previously configured
   `babel-plugin-transform-import-meta` only ever handled `import.meta.url`, never `.env`;
   nothing noticed because no test loaded those modules for real until this tier arrived.

## Running

These live under `src/`, so `npm test` runs them alongside the unit tier. To run the tiers
separately — which is how CI runs them, as two jobs:

```bash
npm run test:integration    # this tier only  (jest --testPathPattern __integration__)
npm run test:unit           # everything else (jest --testPathIgnorePatterns … __integration__)
```

The two partition `npm test` exactly: a new file under `__integration__/` joins the integration
job, anything else joins the unit job. **Run this tier on its own before pushing.** Both bugs
listed above were found that way — a state-leak between tests can hide inside the full run's
ordering and only show up when the tier runs alone, which is the order CI uses.
