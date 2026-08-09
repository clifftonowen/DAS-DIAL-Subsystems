// UNIT (frontend) — DashboardSidebar nav labels.
// NavLink needs a Router in context, so we wrap in MemoryRouter.
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import DashboardSidebar from "../DashboardSidebar";

test("shows the two primary nav links plus Settings", () => {
  render(
    <MemoryRouter>
      <DashboardSidebar />
    </MemoryRouter>
  );

  for (const label of ["Main", "Learners", "Settings"]) {
    expect(screen.getByText(label)).toBeInTheDocument();
  }
});

test("no longer offers a Generate tab", () => {
  render(
    <MemoryRouter>
      <DashboardSidebar />
    </MemoryRouter>
  );

  // Generating an activity is no longer a destination of its own — it happens on the learner's
  // page, against the learner it is for, so there is nothing to navigate to.
  expect(screen.queryByText("Generate")).not.toBeInTheDocument();
});
