// INTEGRATION level 4 (frontend) — UC7 Share Learning Activity.
//
// The ShareWindow -> ShareController message across the real HTTP boundary. ShareWindow and
// lib/api.js are real; MSW replaces only the network. Levels 1-3 are in
// backend/tests/integration/test_uc7_share.py.
//
// WHAT THIS TIER SEES THAT THE UNIT TEST CANNOT. ShareWindow decides whether to offer "Retry"
// from `err.status` (ShareWindow.jsx:53). The unit test mocks `shareActivity` and rejects with an
// error it has attached `.status` to by hand, so the branch appears to work. Across the real
// client it did not: api.js threw a bare `new Error(message)` carrying no status, so every
// failure — including the 400 and 422 that mean "this will never work" — looked retriable. These
// tests assert the behaviour end to end, which is what forced the fix in api.js.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

// createClient runs at import time, so the Supabase module is still mocked; it is the token
// *store*, not the thing under test.
jest.mock("../../lib/supabase", () => ({
  supabase: {
    auth: {
      getSession: async () => ({ data: { session: { access_token: "jwt.test" } } }),
    },
  },
}));

import ShareWindow from "../../components/ShareWindow";
import { server } from "../../test-utils/server";

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const ACTIVITY_ID = "activity-1";
const RECIPIENT = "parent@example.com";

const renderWindow = () =>
  render(<ShareWindow activityId={ACTIVITY_ID} onClose={() => {}} />);

const shareTo = async (user, address) => {
  await user.type(screen.getByLabelText("Recipient email"), address);
  await user.click(screen.getByRole("button", { name: "Send" }));
};

test("IT-7.12: a shared activity crosses the real frontend API boundary", async () => {
  const user = userEvent.setup();
  let received;
  server.use(
    http.post("*/share", async ({ request }) => {
      received = await request.json();
      return HttpResponse.json({ sent: true, activity_id: ACTIVITY_ID,
                                 recipient_email: RECIPIENT });
    }),
  );
  renderWindow();
  await shareTo(user, RECIPIENT);

  expect(await screen.findByText("Activity sent to recipient")).toBeInTheDocument();
  // snake_case on the wire, camelCase in the component — api.js owns that translation.
  expect(received).toEqual({ activity_id: ACTIVITY_ID, recipient_email: RECIPIENT });
});

test("IT-7.13: a malformed address is rejected without reaching the server", async () => {
  const user = userEvent.setup();
  let calls = 0;
  server.use(http.post("*/share", () => { calls += 1; return HttpResponse.json({ sent: true }); }));
  renderWindow();
  // "a@b", NOT something like "not-an-email". The input is type="email", so the browser's own
  // constraint validation blocks anything without an "@" before submit ever fires — a test using
  // one of those would pass while proving only that jsdom implements HTML5. "a@b" is valid to
  // the browser (no TLD required) and invalid to EMAIL_RE, so it is what actually exercises the
  // component's guard, which exists because the two rules genuinely differ.
  await shareTo(user, "a@b");

  // Flow 1a: the client mirrors share_service.py's EMAIL_RE so a bad address costs no round
  // trip. The assertion that matters is the one about `calls` — the message alone would also
  // pass if the request had been sent and rejected.
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Invalid email address, please re-enter");
  expect(calls).toBe(0);
});

test("IT-7.14: a 502 from the email server offers a retry", async () => {
  const user = userEvent.setup();
  server.use(
    http.post("*/share", () =>
      HttpResponse.json({ detail: "the email server refused the message" }, { status: 502 })),
  );
  renderWindow();
  await shareTo(user, RECIPIENT);

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "the email server refused the message");
  // 502 is the gateway failing, not the request being wrong — trying again is reasonable.
  expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
});

test("IT-7.15: a 422 export failure is terminal and does not offer a retry", async () => {
  const user = userEvent.setup();
  server.use(
    http.post("*/share", () =>
      HttpResponse.json({ detail: "Could not export activity as PDF" }, { status: 422 })),
  );
  renderWindow();
  await shareTo(user, RECIPIENT);

  expect(await screen.findByRole("alert")).toHaveTextContent("Could not export activity as PDF");
  // THE CASE THAT WAS BROKEN. 422 means the activity cannot be rendered at all, so retrying
  // sends the therapist round the same loop forever. Before api.js attached `status` to the
  // thrown error this button read "Retry" and the explanatory line below never rendered.
  expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Send" })).toBeInTheDocument();
  expect(screen.getByText(/cannot be exported, so the share was cancelled/)).toBeInTheDocument();
});

test("a 400 from the controller is terminal too", async () => {
  const user = userEvent.setup();
  server.use(
    http.post("*/share", () =>
      HttpResponse.json({ detail: "invalid recipient address" }, { status: 400 })),
  );
  renderWindow();
  // An address the client regex accepts but the server rejects — the only way to reach the
  // controller's own 400, and the reason that validation exists on both sides.
  await shareTo(user, "someone@example.invalid");

  expect(await screen.findByRole("alert")).toHaveTextContent("invalid recipient address");
  expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
});
