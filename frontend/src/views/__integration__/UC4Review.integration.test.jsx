// INTEGRATION level 3 (frontend) — UC4 ReviewSection -> ReviewController.
// ReviewSection and lib/api.js are real. MSW replaces only the HTTP boundary.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

jest.mock("../../lib/supabase", () => ({
  supabase: {
    auth: {
      getSession: async () => ({ data: { session: { access_token: "jwt.test" } } }),
    },
  },
}));

import ReviewSection from "../../components/ReviewSection";
import { server } from "../../test-utils/server";

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function reviewsStartEmpty() {
  server.use(
    http.get("*/reviews/activity-1", () => HttpResponse.json([])),
  );
}

test("IT-4.7: a submitted review crosses the real frontend API boundary", async () => {
  const user = userEvent.setup();
  let received;
  reviewsStartEmpty();
  server.use(
    http.post("*/reviews", async ({ request }) => {
      received = await request.json();
      return HttpResponse.json({
        id: "review-1", activity_id: "activity-1", text: "Useful activity.",
      });
    }),
  );
  render(<ReviewSection activityId="activity-1" />);

  await user.type(screen.getByLabelText("Leave a review"), "Useful activity.");
  await user.click(screen.getByRole("button", { name: "Upload" }));

  expect(await screen.findByText("Useful activity.")).toBeInTheDocument();
  expect(received).toEqual({
    activity_id: "activity-1", text: "Useful activity.", status: null,
  });
});

test("a controller storage error is displayed without adding a review", async () => {
  const user = userEvent.setup();
  reviewsStartEmpty();
  server.use(
    http.post("*/reviews", () =>
      HttpResponse.json({ detail: "Review could not be saved" }, { status: 502 })),
  );
  render(<ReviewSection activityId="activity-1" />);

  await user.type(screen.getByLabelText("Leave a review"), "Useful activity.");
  await user.click(screen.getByRole("button", { name: "Upload" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("Review could not be saved");
  expect(document.querySelectorAll("li")).toHaveLength(0);
});
