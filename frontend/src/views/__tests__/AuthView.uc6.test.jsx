// UNIT (frontend) — UC6 Log In, activation bar AB6.1: AuthView.logIn.
//
// One activation bar with every collaborator mocked: `lib/api` (the
// AuthView -> AuthController message) and `lib/supabase` (which must be mocked
// regardless, because createClient runs at import time).
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// Both factories are self-contained — Jest hoists them above the imports, so they
// cannot reference an outer variable.
jest.mock("../../lib/api", () => ({
  logIn: jest.fn(),
  signUp: jest.fn(),
}));
jest.mock("../../lib/supabase", () => ({
  supabase: { auth: { setSession: jest.fn() } },
}));

import AuthView from "../AuthView";
import { logIn } from "../../lib/api";
import { supabase } from "../../lib/supabase";

const EMAIL = "therapist@das.org.sg";
const PASSWORD = "Passw0rd!";

async function fillAndSubmit(label = "Log in") {
  await userEvent.type(document.querySelector("#email"), EMAIL);
  await userEvent.type(document.querySelector("#password"), PASSWORD);
  await userEvent.click(screen.getByRole("button", { name: label }));
}

beforeEach(() => {
  logIn.mockReset();
  supabase.auth.setSession.mockReset();
});

test("UT-6.1: valid credentials establish the session and notify the app", async () => {
  logIn.mockResolvedValue({ access_token: "jwt.test", refresh_token: "rt.test" });
  const onAuthed = jest.fn();
  render(<AuthView onAuthed={onAuthed} />);

  await fillAndSubmit();

  expect(logIn).toHaveBeenCalledTimes(1);
  expect(logIn).toHaveBeenCalledWith(EMAIL, PASSWORD);
  // The tokens from AuthController are what establish the browser session.
  expect(supabase.auth.setSession).toHaveBeenCalledWith({
    access_token: "jwt.test",
    refresh_token: "rt.test",
  });
  expect(onAuthed).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("UT-6.2: rejected credentials render the controller's message and stay put", async () => {
  // api.js now surfaces FastAPI's `detail`, so the view can show a real reason
  // rather than a status-derived string.
  logIn.mockRejectedValue(new Error("Invalid email or password"));
  const onAuthed = jest.fn();
  render(<AuthView onAuthed={onAuthed} />);

  await fillAndSubmit();

  expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password");
  expect(supabase.auth.setSession).not.toHaveBeenCalled();
  expect(onAuthed).not.toHaveBeenCalled();
  // The form stays mounted with the entered email preserved.
  expect(document.querySelector("#email")).toHaveValue(EMAIL);
  expect(screen.getByRole("button", { name: "Log in" })).toBeInTheDocument();
});
