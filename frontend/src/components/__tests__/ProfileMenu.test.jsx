// UNIT (frontend) — ProfileMenu component in isolation.
// The real Supabase client is mocked so nothing hits the network; we assert the
// avatar/email render and that "Sign out" delegates to supabase.auth.signOut.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// Mock the module ProfileMenu imports as "../lib/supabase".
jest.mock("../../lib/supabase", () => ({
  supabase: { auth: { signOut: jest.fn() } },
}));

import ProfileMenu from "../ProfileMenu";
import { supabase } from "../../lib/supabase";

const session = { user: { email: "owen@example.com" } };

test("renders the My Profile trigger with the email initial", () => {
  render(<ProfileMenu session={session} />);
  expect(screen.getByText("My Profile")).toBeInTheDocument();
  expect(screen.getAllByText("O").length).toBeGreaterThan(0); // avatar initial
});

test("opens the dropdown and shows the signed-in email", async () => {
  render(<ProfileMenu session={session} />);
  await userEvent.click(screen.getByText("My Profile"));
  expect(screen.getByText("owen@example.com")).toBeInTheDocument();
});

test("clicking Sign out calls supabase.auth.signOut", async () => {
  supabase.auth.signOut.mockClear();
  render(<ProfileMenu session={session} />);
  await userEvent.click(screen.getByText("My Profile"));
  await userEvent.click(screen.getByText("Sign out"));
  expect(supabase.auth.signOut).toHaveBeenCalledTimes(1);
});
