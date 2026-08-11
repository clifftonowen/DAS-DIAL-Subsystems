// Regression test for the UC4 decision hand-off.
import { submitReview } from "../api";
import { supabase } from "../supabase";

jest.mock("../supabase", () => ({
  supabase: { auth: { getSession: jest.fn() } },
}));

beforeEach(() => {
  supabase.auth.getSession.mockResolvedValue({ data: { session: null } });
  global.fetch = jest.fn().mockResolvedValue({
    ok: true,
    json: jest.fn().mockResolvedValue({}),
  });
});

test("passes the selected approval status in the review request", async () => {
  await submitReview("activity-1", "Useful activity.", "APPROVED");

  expect(fetch).toHaveBeenCalledWith(
    "http://localhost:8000/reviews",
    expect.objectContaining({
      method: "POST",
      body: JSON.stringify({
        activity_id: "activity-1", text: "Useful activity.",
        approval_status: "APPROVED",
      }),
    }),
  );
});
