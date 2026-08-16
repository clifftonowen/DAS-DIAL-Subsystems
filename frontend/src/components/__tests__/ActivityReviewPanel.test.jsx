// UNIT (frontend) — ActivityReviewPanel shows UC3's automated verdict on the last activity.
//
// The load-bearing property is the one the component's own comment argues for: this panel reports
// what the ValidativeAgent decided, never what a therapist decided. UC4's human approval lives on
// `reviews.approval_status` and renders in ReviewSection. So the labels here must stay in UC3's
// vocabulary ("Validated" / "Flagged for review"), and must never borrow UC4's ("Approve" /
// "Not approved") — otherwise the screen collapses two separate claims into one.
//
// ActivityContent is rendered for real rather than mocked: it is pure, and the delegation is
// part of what this component does.

import { render, screen } from "@testing-library/react";
import ActivityReviewPanel from "../ActivityReviewPanel";

const activity = (over = {}) => ({
  id: "activity-1",
  status: "VALIDATED",
  literacy_objective: "Blend CVC words",
  content: { text: "Clap the rhyme." },
  ...over,
});

test.each([
  ["VALIDATED", "Validated"],
  ["FLAGGED", "Flagged for review"],
  ["GENERATED", "Not yet reviewed"],
])("labels the %s verdict as %s", (status, label) => {
  render(<ActivityReviewPanel activity={activity({ status })} />);

  expect(screen.getByText(label)).toBeInTheDocument();
  expect(screen.getByText("Last generated activity")).toBeInTheDocument();
});

test.each(["VALIDATED", "FLAGGED", "GENERATED"])(
  "never states a therapist decision for %s — that is UC4's, not this panel's",
  (status) => {
    render(<ActivityReviewPanel activity={activity({ status })} />);

    // The exact wording ReviewSection uses for the human verdict. None of it belongs here.
    for (const uc4 of [/approved/i, /rejected/i, /^approve$/i]) {
      expect(screen.queryByText(uc4)).not.toBeInTheDocument();
    }
  },
);

test("treats a row with no status as not yet reviewed", () => {
  // Rows generated before `status` existed carry none; they are not a fourth verdict.
  render(<ActivityReviewPanel activity={activity({ status: undefined })} />);

  expect(screen.getByText("Not yet reviewed")).toBeInTheDocument();
});

test("shows an unrecognised status verbatim rather than mislabelling it", () => {
  render(<ActivityReviewPanel activity={activity({ status: "ARCHIVED" })} />);

  expect(screen.getByText("ARCHIVED")).toBeInTheDocument();
  expect(screen.queryByText("Validated")).not.toBeInTheDocument();
});

test("renders the literacy objective when the activity carries one", () => {
  render(<ActivityReviewPanel activity={activity()} />);

  expect(screen.getByText("Blend CVC words")).toBeInTheDocument();
});

test("omits the objective line when there is none, rather than rendering an empty one", () => {
  const { container } = render(
    <ActivityReviewPanel activity={activity({ literacy_objective: null })} />,
  );

  expect(screen.getByText("Last generated activity")).toBeInTheDocument();
  expect(screen.queryByText("Blend CVC words")).not.toBeInTheDocument();
  // The objective is conditional, so its absence must mean no element at all — not a blank line
  // holding open the space where it would have been.
  const blank = [...container.querySelectorAll("p")].filter((p) => !p.textContent.trim());
  expect(blank).toHaveLength(0);
});

test("passes the activity text through to ActivityContent", () => {
  render(
    <ActivityReviewPanel
      activity={activity({ content: { text: "## Warm-up\nClap the rhyme." } })}
    />,
  );

  // Formatted by ActivityContent, so the heading marker must not survive to the screen.
  expect(screen.getByText("Warm-up")).toBeInTheDocument();
  expect(screen.getByText("Clap the rhyme.")).toBeInTheDocument();
  expect(screen.queryByText(/##/)).not.toBeInTheDocument();
});

test("renders without a content payload at all", () => {
  // `content` is nullable on the row; the panel still has a verdict worth showing.
  render(<ActivityReviewPanel activity={activity({ content: null })} />);

  expect(screen.getByText("Validated")).toBeInTheDocument();
  expect(screen.getByText("Last generated activity")).toBeInTheDocument();
});
