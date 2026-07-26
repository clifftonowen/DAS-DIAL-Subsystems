// INTEGRATION level 4 (frontend) — UC8 Sign Up.
//
// The AuthView -> AuthController `signUp` message across the real HTTP boundary.
// MSW intercepts the network rather than the module, so `lib/api.js` is REAL code
// under test. Levels 1-3 are in backend/tests/integration/test_uc8_sign_up.py.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

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

const NEW_EMAIL = "new.therapist@das.org.sg";
const PASSWORD = "Passw0rd!";

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  server.resetHandlers();
  supabase.auth.setSession.mockReset();
});
afterAll(() => server.close());

async function switchToSignUpAndSubmit() {
  await userEvent.click(screen.getByRole("button", { name: "Need an account? Sign up" }));
  await userEvent.type(document.querySelector("#email"), NEW_EMAIL);
  await userEvent.type(document.querySelector("#password"), PASSWORD);
  await userEvent.click(screen.getByRole("button", { name: "Sign up" }));
}

test("IT-8.8: POST /auth/signup is issued and the success state renders", async () => {
  let received;
  server.use(
    http.post("*/auth/signup", async ({ request }) => {
      received = await request.json();
      return HttpResponse.json({
        user_id: "22222222-2222-4222-8222-222222222222",
        email: NEW_EMAIL,
        email_confirmation_required: true,
      });
    })
  );
  const onAuthed = jest.fn();
  render(<AuthView onAuthed={onAuthed} />);

  await switchToSignUpAndSubmit();

  expect(received).toEqual({ email: NEW_EMAIL, password: PASSWORD });
  expect(await screen.findByRole("status")).toHaveTextContent(
    "Account is successfully created."
  );
  // Still unauthenticated until the therapist confirms and logs in.
  expect(supabase.auth.setSession).not.toHaveBeenCalled();
  expect(onAuthed).not.toHaveBeenCalled();
});

test("IT-8.9: a 400 detail from AuthController reaches the user", async () => {
  server.use(
    http.post("*/auth/signup", () =>
      HttpResponse.json({ detail: "User already registered" }, { status: 400 }))
  );
  const onAuthed = jest.fn();
  render(<AuthView onAuthed={onAuthed} />);

  await switchToSignUpAndSubmit();

  expect(await screen.findByRole("alert")).toHaveTextContent("User already registered");
  // The form stays mounted in signup mode; no navigation occurs.
  expect(screen.getByRole("button", { name: "Sign up" })).toBeInTheDocument();
  expect(onAuthed).not.toHaveBeenCalled();
});
