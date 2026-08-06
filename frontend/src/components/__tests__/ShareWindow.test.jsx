// UNIT (frontend) — Share Learning Activity and the Dashboard activation bar.


import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// Jest hoists this above the imports, so the factory must be self-contained.
jest.mock("../../lib/api", () => ({
  shareActivity: jest.fn(),
}));

import ShareWindow from "../ShareWindow";
import { shareActivity } from "../../lib/api";

const VALID_EMAIL = "parent@example.com";
const ACTIVITY_ID = "act-1";

/** build the Error that lib/api throws for a failed response. */
function apiError(message, status) {
  const err = new Error(message);
  err.status = status;
  return err;
}

function renderWindow() {
  const onClose = jest.fn();
  render(<ShareWindow activityId={ACTIVITY_ID} activityName="Rhyme sort" onClose={onClose} />);
  return { onClose };
}

async function enterAndSend(email, buttonName = "Send") {
  await userEvent.type(screen.getByLabelText("Recipient email"), email);
  await userEvent.click(screen.getByRole("button", { name: buttonName }));
}

beforeEach(() => {
  shareActivity.mockReset();
});

// UT-7.14 — invalid email address

test("UT-7.14: an invalid address is rejected and re-entry is prompted", async () => {
  renderWindow();
  await enterAndSend("a@b");
  expect(screen.getByRole("alert")).toHaveTextContent("Invalid email address, please re-enter");
  expect(shareActivity).not.toHaveBeenCalled();
  expect(screen.getByLabelText("Recipient email")).toBeInTheDocument();
  expect(screen.queryByText("Activity sent to recipient")).not.toBeInTheDocument();
});

test("UT-7.14: correcting the address clears the error", async () => {
  renderWindow();
  await enterAndSend("a@b");
  await userEvent.type(screen.getByLabelText("Recipient email"), "x");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("UT-7.14: a malformed address never reaches the controller at all", async () => {
  renderWindow();

  await enterAndSend("not-an-email");

  expect(shareActivity).not.toHaveBeenCalled();
  expect(screen.queryByText("Activity sent to recipient")).not.toBeInTheDocument();
});


// UT-7.15 — success

test("UT-7.15: a successful share confirms it to the therapist", async () => {
  shareActivity.mockResolvedValue({ sent: true, activity_id: ACTIVITY_ID });
  renderWindow();

  await enterAndSend(VALID_EMAIL);

  expect(shareActivity).toHaveBeenCalledTimes(1);
  expect(shareActivity).toHaveBeenCalledWith(ACTIVITY_ID, VALID_EMAIL);
  expect(screen.getByText("Activity sent to recipient")).toBeInTheDocument();
  expect(screen.getByText(VALID_EMAIL)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Send" })).not.toBeInTheDocument();
});

test("UT-7.15: a pasted address with stray spaces is trimmed before sending", async () => {
  shareActivity.mockResolvedValue({ sent: true });
  renderWindow();

  await enterAndSend(`  ${VALID_EMAIL}  `);

  expect(shareActivity).toHaveBeenCalledWith(ACTIVITY_ID, VALID_EMAIL);
});


// UT-7.16 — export error (flow 2a: abort, no retry)

test("UT-7.16: an export error is shown and the share is abandoned", async () => {
  shareActivity.mockRejectedValue(apiError("Could not export activity as PDF", 422));
  renderWindow();

  await enterAndSend(VALID_EMAIL);
  expect(screen.getByRole("alert")).toHaveTextContent("Could not export activity as PDF");
  expect(screen.queryByText("Activity sent to recipient")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  expect(screen.getByRole("alert")).toHaveTextContent("the share was cancelled");
});


// UT-7.17 — send error (flow 4a: notify and offer retry)

test("UT-7.17: a send error is shown with a retry option", async () => {
  shareActivity.mockRejectedValue(apiError("Could not send activity", 502));
  renderWindow();

  await enterAndSend(VALID_EMAIL);

  expect(screen.getByRole("alert")).toHaveTextContent("Could not send activity");
  expect(screen.queryByText("Activity sent to recipient")).not.toBeInTheDocument();
  // 4a explicitly offers a retry, so the submit button changes label.
  expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
});

test("UT-7.17: pressing Retry sends the same request again", async () => {
  shareActivity.mockRejectedValueOnce(apiError("Could not send activity", 502));
  renderWindow();
  await enterAndSend(VALID_EMAIL);

  shareActivity.mockResolvedValueOnce({ sent: true });
  await userEvent.click(screen.getByRole("button", { name: "Retry" }));

  expect(shareActivity).toHaveBeenCalledTimes(2);
  expect(shareActivity).toHaveBeenLastCalledWith(ACTIVITY_ID, VALID_EMAIL);
  expect(screen.getByText("Activity sent to recipient")).toBeInTheDocument();
});