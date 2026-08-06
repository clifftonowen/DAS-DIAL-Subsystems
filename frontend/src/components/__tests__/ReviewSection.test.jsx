// UNIT (UC4) — Dashboard review section, with the API module mocked.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ReviewSection from "../ReviewSection";
import { getReviews, submitReview } from "../../lib/api";

jest.mock("../../lib/api", () => ({
  getReviews: jest.fn(),
  submitReview: jest.fn(),
}));

beforeEach(() => {
  jest.clearAllMocks();
  getReviews.mockResolvedValue([]);
});

test("UT-4.9 enables Upload when the therapist has written a review", async () => {
  const user = userEvent.setup();
  render(<ReviewSection activityId="activity-1" />);

  const upload = screen.getByRole("button", { name: "Upload" });
  expect(upload).toBeDisabled();
  await user.type(screen.getByLabelText("Leave a review"), "Useful activity.");

  expect(upload).toBeEnabled();
});

test("UT-4.10 displays a successfully submitted review beside the activity", async () => {
  const user = userEvent.setup();
  submitReview.mockResolvedValue({ id: "review-1", text: "Useful activity." });
  render(<ReviewSection activityId="activity-1" />);

  const text = screen.getByLabelText("Leave a review");
  await user.type(text, "Useful activity.");
  await user.click(screen.getByRole("button", { name: "Upload" }));

  expect(await screen.findByText("Useful activity.")).toBeInTheDocument();
  expect(submitReview).toHaveBeenCalledWith("activity-1", "Useful activity.", null);
  expect(text).toHaveValue("");
});

test("UT-4.11 shows the save error and keeps the review off the list", async () => {
  const user = userEvent.setup();
  submitReview.mockRejectedValue(new Error("Review could not be saved"));
  render(<ReviewSection activityId="activity-1" />);

  await user.type(screen.getByLabelText("Leave a review"), "Useful activity.");
  await user.click(screen.getByRole("button", { name: "Upload" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("Review could not be saved");
  expect(document.querySelectorAll("li")).toHaveLength(0);
});
