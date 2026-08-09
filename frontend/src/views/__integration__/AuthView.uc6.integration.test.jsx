// INTEGRATION level 4 (frontend) — UC6 Log In.
//
// The top of the bottom-up call graph: the AuthView -> AuthController message,
// exercised across the real HTTP boundary. MSW intercepts the network rather than
// the module, so `lib/api.js` is REAL code under test here — which matters,
// because that is where request shaping and error handling live. Levels 1-3 are
// in backend/tests/integration/test_uc6_log_in.py.
//
// Only the driver at the boundary is faked: the backend is replaced at the
// network edge. The browser is not involved, which is what keeps this an
// integration test rather than a system test.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

// createClient runs at import time, so the Supabase module is still mocked; it is
// the token *store*, not the thing under test.
jest.mock("../../lib/supabase", () => ({
  supabase: {
    auth: {
      setSession: jest.fn(),
      getSession: async () => ({ data: { session: null } }),
    },
  },
}));

import { server } from "../../test-utils/server";
import AuthView from "../AuthView";
import { supabase } from "../../lib/supabase";

const EMAIL = "therapist@das.org.sg";
const PASSWORD = "Passw0rd!";

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  server.resetHandlers();
  supabase.auth.setSession.mockReset();
});
afterAll(() => server.close());

async function fillAndSubmit() {
  await userEvent.type(document.querySelector("#email"), EMAIL);
  await userEvent.type(document.querySelector("#password"), PASSWORD);
  await userEvent.click(screen.getByRole("button", { name: "Log in" }));
}

test("IT-6.9: POST /auth/login is issued with the right body and the session is stored", async () => {
  let received;
  server.use(
    http.post("*/auth/login", async ({ request }) => {
      received = await request.json();
      return HttpResponse.json({
        user_id: "11111111-1111-4111-8111-111111111111",
        email: EMAIL,
        access_token: "jwt.test",
        refresh_token: "rt.test",
      });
    })
  );
  const onAuthed = jest.fn();
  render(<AuthView onAuthed={onAuthed} />);

  await fillAndSubmit();

  // The request actually went out, with the JSON body AuthController expects.
  expect(received).toEqual({ email: EMAIL, password: PASSWORD });
  // The token from the response is what establishes the session.
  expect(supabase.auth.setSession).toHaveBeenCalledWith({
    access_token: "jwt.test",
    refresh_token: "rt.test",
  });
  expect(onAuthed).toHaveBeenCalledTimes(1);
});

test("IT-6.10: a 401 detail from AuthController reaches the user", async () => {
  // This is the case the old api.js could not pass: it threw
  // Error("401 Unauthorized") and discarded the body, so `detail` never arrived.
  server.use(
    http.post("*/auth/login", () =>
      HttpResponse.json({ detail: "Invalid email or password" }, { status: 401 }))
  );
  const onAuthed = jest.fn();
  render(<AuthView onAuthed={onAuthed} />);

  await fillAndSubmit();

  expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password");
  expect(supabase.auth.setSession).not.toHaveBeenCalled();
  expect(onAuthed).not.toHaveBeenCalled();
});
