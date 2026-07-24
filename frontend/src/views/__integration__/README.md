# Frontend integration tests (Jest + MSW)

**Status: scaffolded, not yet implemented.** `LearnersPage.integration.test.jsx` holds
`test.todo` placeholders — fill them in as views gain real behavior.

## What these are

Integration tests render a **whole view (or a subtree of components) with routing real** and only
the **network** mocked. They sit between:

- **unit** (`frontend/src/components/__tests__/`) — one component, every collaborator mocked, and
- **system** (`backend/tests/system/`, Selenium) — the real browser against the real backend.

They run in Jest/jsdom, so they're fast and deterministic (no browser, no live backend), and they
catch things unit tests can't: data-fetching + rendering + filtering + navigation working together.

## The tool: MSW (Mock Service Worker)

Instead of mocking `lib/api.js` function-by-function, MSW intercepts the real `fetch` calls the app
makes and returns canned JSON. That means the component under test runs its **actual** data path.

### One-time setup (when you're ready to implement)

```bash
cd frontend
npm i -D msw
```

Create shared handlers matching the routes in `src/lib/api.js` (base `VITE_API_URL`):

```js
// src/test-utils/handlers.js
import { http, HttpResponse } from "msw";

const BASE = "http://localhost:8000";           // matches lib/api.js default
export const handlers = [
  http.get(`${BASE}/learners`, () =>
    HttpResponse.json([
      { id: "l1", name: "Ada", band: "A" },
      { id: "l2", name: "Bo",  band: "B" },
    ])),
  http.get(`${BASE}/learners/:id`, ({ params }) =>
    HttpResponse.json({ id: params.id, name: "Ada" })),
];
```

```js
// src/test-utils/server.js
import { setupServer } from "msw/node";
import { handlers } from "./handlers";
export const server = setupServer(...handlers);
```

## Writing a test

```jsx
// src/views/__integration__/LearnersPage.integration.test.jsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { server } from "../../test-utils/server";
import LearnersPage from "../LearnersPage";

// Mock Supabase auth (api.js reads a token from it before every fetch).
jest.mock("../../lib/supabase", () => ({
  supabase: { auth: { getSession: async () => ({ data: { session: { access_token: "t" } } }) } },
}));

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

test("renders the learners fetched from the API", async () => {
  render(<MemoryRouter><LearnersPage /></MemoryRouter>);
  expect(await screen.findByText("Ada")).toBeInTheDocument();
  expect(screen.getByText("Bo")).toBeInTheDocument();
});

test("shows an error state when the request fails", async () => {
  server.use(http.get("*/learners", () => HttpResponse.error()));
  render(<MemoryRouter><LearnersPage /></MemoryRouter>);
  // assert your error UI, e.g. await screen.findByText(/failed|error/i)
});
```

Notes:
- Wrap in `MemoryRouter` so navigation (`useNavigate`, `<Link>`) works; assert the URL or the
  destination page after a click.
- Use `findBy*` / `waitFor` for anything that appears after the fetch resolves.

## Running

These live under `src/`, so `npm test` already discovers them (currently as `todo`). Once real,
they run alongside unit tests. If you later want them isolated (separate MSW setup, own CI job),
split them into a Jest **project** or add a `"test:integration"` script filtering
`*.integration.test.jsx`.
