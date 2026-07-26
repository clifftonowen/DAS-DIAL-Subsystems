// UNIT (frontend) — UC8 Sign Up, activation bar AB8.1: AuthView.signUp.
//
// The sign-up affordance is the ghost "Need an account? Sign up" button, which
// flips AuthView into signup mode; the submit button then reads "Sign up".
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

jest.mock("../../lib/api", () => ({
  logIn: jest.fn(),
  signUp: jest.fn(),
}));
jest.mock("../../lib/supabase", () => ({
  supabase: { auth: { setSession: jest.fn() } },
}));

import AuthView from "../AuthView";
import { signUp } from "../../lib/api";
import { supabase } from "../../lib/supabase";

const NEW_EMAIL = "new.therapist@das.org.sg";
const PASSWORD = "Passw0rd!";

async function switchToSignUpAndSubmit() {
  await userEvent.click(screen.getByRole("button", { name: "Need an account? Sign up" }));
  await userEvent.type(document.querySelector("#email"), NEW_EMAIL);
  await userEvent.type(document.querySelector("#password"), PASSWORD);
  await userEvent.click(screen.getByRole("button", { name: "Sign up" }));
}

beforeEach(() => {
  signUp.mockReset();
  supabase.auth.setSession.mockReset();
});

test("UT-8.1: a new account is confirmed and the view returns to the login form", async () => {
  // Email confirmation on: the account exists but no session is issued, so the
  // therapist stays signed out until they log in — UC8's postcondition.
  signUp.mockResolvedValue({
    user_id: "22222222-2222-4222-8222-222222222222",
    email: NEW_EMAIL,
    email_confirmation_required: true,
  });
  const onAuthed = jest.fn();
  render(<AuthView onAuthed={onAuthed} />);

  await switchToSignUpAndSubmit();

  expect(signUp).toHaveBeenCalledTimes(1);
  expect(signUp).toHaveBeenCalledWith(NEW_EMAIL, PASSWORD);
  expect(await screen.findByRole("status")).toHaveTextContent(
    "Account is successfully created."
  );
  // Back on the login form, still unauthenticated.
  expect(screen.getByRole("button", { name: "Log in" })).toBeInTheDocument();
  expect(onAuthed).not.toHaveBeenCalled();
});

test("UT-8.2: a duplicate email renders the controller's message, no navigation", async () => {
  signUp.mockRejectedValue(new Error("User already registered"));
  const onAuthed = jest.fn();
  render(<AuthView onAuthed={onAuthed} />);

  await switchToSignUpAndSubmit();

  expect(await screen.findByRole("alert")).toHaveTextContent("User already registered");
  expect(supabase.auth.setSession).not.toHaveBeenCalled();
  expect(onAuthed).not.toHaveBeenCalled();
  // The form stays mounted in signup mode with the entered email preserved.
  expect(document.querySelector("#email")).toHaveValue(NEW_EMAIL);
  expect(screen.getByRole("button", { name: "Sign up" })).toBeInTheDocument();
});
