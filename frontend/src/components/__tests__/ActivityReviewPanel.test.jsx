// UNIT (frontend) — ActivityReviewPanel displays validated and flagged states (UC3).
//
// Two claims:
//   UT-3.12  A validated activity is displayed with an "Approved" badge (ready state).
//   UT-3.13  A flagged activity is displayed with a "Not approved" badge (review state).
//
// The component itself is a pure display; no API calls are made here.

import { render, screen } from "@testing-library/react";
import ActivityReviewPanel from "../ActivityReviewPanel";

const baseActivity = {
  id: "act-1",
  learner_id: "11111111-1111-1111-1111-111111111111",
  content: { text: "Title: Rhyme Time\n1. Clap the rhyme.\n2. Say the onset." },
  literacy_objective: "short vowels",
};

// ── UT-3.12  Displays validated activity in ready state ──────────────────────
test("UT-3.12 — shows 'Approved' badge for a VALIDATED activity", () => {
  render(<ActivityReviewPanel activity={{ ...baseActivity, status: "VALIDATED" }} />);

  expect(screen.getByText("Approved")).toBeInTheDocument();
  expect(screen.getByText("Last generated activity")).toBeInTheDocument();
  expect(screen.getByText("short vowels")).toBeInTheDocument();
});

// ── UT-3.13  Displays flagged activity in review state ───────────────────────
test("UT-3.13 — shows 'Not approved' badge for a FLAGGED activity", () => {
  render(<ActivityReviewPanel activity={{ ...baseActivity, status: "FLAGGED" }} />);

  expect(screen.getByText("Not approved")).toBeInTheDocument();
  expect(screen.getByText("Last generated activity")).toBeInTheDocument();
});

// ── edge case: no status falls back to "Not yet reviewed" ────────────────────
test("shows 'Not yet reviewed' when activity has no status", () => {
  render(<ActivityReviewPanel activity={{ ...baseActivity }} />);

  expect(screen.getByText("Not yet reviewed")).toBeInTheDocument();
});

// ── edge case: GENERATED is the pre-review state ─────────────────────────────
test("shows 'Not yet reviewed' for a GENERATED activity", () => {
  render(<ActivityReviewPanel activity={{ ...baseActivity, status: "GENERATED" }} />);

  expect(screen.getByText("Not yet reviewed")).toBeInTheDocument();
});
