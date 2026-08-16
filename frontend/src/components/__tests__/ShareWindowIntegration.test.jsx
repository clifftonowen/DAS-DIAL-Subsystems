// FRONTEND INTEGRATION  — Share Learning Activity

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

// createClient runs at import time, so the Supabase module is still mocked — it
// is the token store api.js reads from, not the thing under test.
jest.mock("../../lib/supabase", () => ({
  supabase: {
    auth: {
      getSession: async () => ({ data: { session: { access_token: "jwt.test" } } }),
    },
  },
}));

import { server } from "../../test-utils/server";
import ShareWindow from "../ShareWindow";

const ACTIVITY_ID = "act-1";
const VALID_EMAIL = "parent@example.com";

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function renderWindow() {
  render(<ShareWindow activityId={ACTIVITY_ID} activityName="Rhyme sort" onClose={jest.fn()} />);
}

async function enterAndSend(email, buttonName = "Send") {
  await userEvent.type(screen.getByLabelText("Recipient email"), email);
  await userEvent.click(screen.getByRole("button", { name: buttonName }));
}


// IT-7.8 — the operational flow across the network boundary

test("IT-7.8: POST /share carries the activity and recipient, and the therapist is told", async () => {
  let received;
  let authorization;
  server.use(
    http.post("*/share", async ({ request }) => {
      received = await request.json();
      authorization = request.headers.get("Authorization");
      return HttpResponse.json({
        sent: true, activity_id: ACTIVITY_ID,
        recipient_email: VALID_EMAIL, pdf_bytes: 118432,
      });
    })
  );
  renderWindow();

  await enterAndSend(VALID_EMAIL);

  // The body ShareController expects — snake_case, shaped by lib/api.js.
  expect(received).toEqual({
    activity_id: ACTIVITY_ID,
    recipient_email: VALID_EMAIL,
  });
  // The endpoint is authenticated, so the session token must ride along.
  expect(authorization).toBe("Bearer jwt.test");
  expect(screen.getByText("Activity sent to recipient")).toBeInTheDocument();
});


// IT-7.9 — invalid address (alternative flow 1a)

test("IT-7.9: an invalid address never reaches the network", async () => {
  let called = false;
  server.use(
    http.post("*/share", () => {
      called = true;
      return HttpResponse.json({ sent: true });
    })
  );
  renderWindow();

  await enterAndSend("a@b");

  expect(called).toBe(false);
  expect(screen.getByRole("alert")).toHaveTextContent(
    "Invalid email address, please re-enter");
});


// IT-7.10 — export failure (alternative flow 2a: abort)

test("IT-7.10: a 422 detail reaches the therapist, with no retry offered", async () => {
  server.use(
    http.post("*/share", () =>
      HttpResponse.json({ detail: "Could not export activity as PDF" }, { status: 422 }))
  );
  renderWindow();

  await enterAndSend(VALID_EMAIL);

  
  expect(screen.getByRole("alert")).toHaveTextContent("Could not export activity as PDF");
  // And that it attached err.status, which is what suppresses the Retry button.
  expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  expect(screen.queryByText("Activity sent to recipient")).not.toBeInTheDocument();
});


// IT-7.11 — send failure (alternative flow 4a: notify and offer retry)

test("IT-7.11: a 502 detail reaches the therapist, with a retry offered", async () => {
  server.use(
    http.post("*/share", () =>
      HttpResponse.json({ detail: "Could not send activity" }, { status: 502 }))
  );
  renderWindow();

  await enterAndSend(VALID_EMAIL);

  expect(screen.getByRole("alert")).toHaveTextContent("Could not send activity");
  // 502 is retriable where 422 is not — the one behavioural difference between
  // IT-7.10 and IT-7.11, and it depends entirely on api.js setting err.status.
  expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
});