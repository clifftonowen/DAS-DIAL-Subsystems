// UNIT (frontend) — GeneratePage renders the three outcomes of a generation request.
//
// The API module is mocked, so this asserts the page's contract with the backend: it searches
// SERVER-SIDE, sends the selected learner's id (their marks are read server-side) and
// distinguishes a grounded activity from a 200-with-refusal from a thrown error.

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import GeneratePage from "../GeneratePage";
import { listLearners, generateActivity } from "../../lib/api";

jest.mock("../../lib/api", () => ({
  listLearners: jest.fn(),
  generateActivity: jest.fn(),
}));

const LEARNER = { id: "learner-1", pseudonym: "Ali", band: "A1", on_caseload: true };

// Type the learner's name, pick them from the dropdown, then hit Generate.
async function selectAndGenerate(user) {
  await user.type(screen.getByPlaceholderText("Type a learner's name…"), "Ali");
  await user.click(await screen.findByText("Ali"));
  await user.click(screen.getByRole("button", { name: "Generate" }));
}

beforeEach(() => {
  jest.clearAllMocks();
  listLearners.mockResolvedValue({ items: [LEARNER], total: 1, page: 1, per_page: 20 });
});

test("sends the learner id and renders the activity with its grounding sources", async () => {
  const user = userEvent.setup();
  generateActivity.mockResolvedValue({
    status: "GENERATED",
    content: "Title: Rhyme Time\n1. Clap the rhyme.",
    query: "literacy activity targeting decoding and spelling",
    learner_id: "learner-1",
    grounding: [
      { title: "Rhyme Time", source: "a.pdf", page: 4, concept: "onset_rime",
        stage: "practice", similarity: 0.712 },
    ],
  });

  render(<GeneratePage />);
  await selectAndGenerate(user);

  expect(generateActivity).toHaveBeenCalledWith("learner-1", { band: "A1", notes: "" });
  expect(await screen.findByText(/Clap the rhyme/)).toBeInTheDocument();
  expect(screen.getByText("Grounded in 1 source")).toBeInTheDocument();
  expect(screen.getByText("Rhyme Time")).toBeInTheDocument();
  expect(screen.getByText("a.pdf p.4 · onset_rime · practice")).toBeInTheDocument();
  expect(screen.getByText("0.71")).toBeInTheDocument();
});

test("shows the refusal reason when the curriculum does not cover the request", async () => {
  const user = userEvent.setup();
  generateActivity.mockResolvedValue({
    status: "INSUFFICIENT_CONTEXT",
    content: "",
    reason: "best similarity 0.310 is below the 0.5 gate.",
    query: "literacy activity targeting decoding and spelling",
    learner_id: "learner-1",
    grounding: [],
  });

  render(<GeneratePage />);
  await selectAndGenerate(user);

  expect(await screen.findByText("Not enough curriculum grounding")).toBeInTheDocument();
  expect(screen.getByText(/below the 0.5 gate/)).toBeInTheDocument();
});

test("tells the therapist to upload scores when the learner has none", async () => {
  const user = userEvent.setup();
  generateActivity.mockResolvedValue({
    status: "INSUFFICIENT_CONTEXT", content: "", reason: "…",
    query: "", learner_id: "learner-1", grounding: [],
  });

  render(<GeneratePage />);
  await selectAndGenerate(user);

  expect(await screen.findByText("This learner has no assessment scores yet")).toBeInTheDocument();
  expect(screen.getByText(/there are none on record/)).toBeInTheDocument();
});

test("surfaces a failed request separately from a refusal", async () => {
  const user = userEvent.setup();
  jest.spyOn(console, "error").mockImplementation(() => {});
  generateActivity.mockRejectedValue(new Error("500 Internal Server Error"));

  render(<GeneratePage />);
  await selectAndGenerate(user);

  expect(await screen.findByText("Could not generate activity")).toBeInTheDocument();
  expect(screen.getByText("500 Internal Server Error")).toBeInTheDocument();
  await waitFor(() => expect(screen.queryByText(/no profile yet/)).not.toBeInTheDocument());
});
