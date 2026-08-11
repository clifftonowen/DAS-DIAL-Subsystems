// Default MSW handlers, matching the routes in src/lib/api.js.
//
// Under Jest `import.meta.env` is undefined, so api.js falls back to
// http://localhost:8000. Handlers use `*` wildcards so they match whatever base
// URL is in play and don't silently miss if VITE_API_URL is ever set.
//
// KEEP THESE SHAPES HONEST. A default handler that returns the wrong shape is worse than no
// default at all: the request is intercepted, so `onUnhandledRequest: "error"` stays quiet, the
// view renders its empty state, and the test passes for the wrong reason. This one previously
// returned a bare array while `listLearners` reads `{ items, total }`, which would have made
// every LearnersPage assertion agree with an empty grid.
import { http, HttpResponse } from "msw";

// GET /learners is paged and searched server-side; api.js resolves the envelope, not a bare list.
export const learnerPage = (items = [], overrides = {}) => ({
  items,
  total: items.length,
  page: 1,
  per_page: 24,
  ...overrides,
});

export const handlers = [
  http.get("*/learners", () =>
    HttpResponse.json(
      learnerPage([
        { id: "l1", student_id: "S-001", pseudonym: "Ada", tier: "Tier 2",
          on_caseload: true, band: "A2", band_group: "A" },
        { id: "l2", student_id: "S-002", pseudonym: "Bo", tier: "Tier 1",
          on_caseload: true, band: "B4", band_group: "B" },
      ])
    )),
];
