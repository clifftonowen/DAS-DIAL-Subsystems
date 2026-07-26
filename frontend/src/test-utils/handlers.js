// Default MSW handlers, matching the routes in src/lib/api.js.
//
// Under Jest `import.meta.env` is undefined, so api.js falls back to
// http://localhost:8000. Handlers use `*` wildcards so they match whatever base
// URL is in play and don't silently miss if VITE_API_URL is ever set.
import { http, HttpResponse } from "msw";

export const handlers = [
  http.get("*/learners", () =>
    HttpResponse.json([
      { id: "l1", pseudonym: "Ada", band_level: "A" },
      { id: "l2", pseudonym: "Bo", band_level: "B" },
    ])),
];
