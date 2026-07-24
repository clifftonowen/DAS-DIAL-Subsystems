// UNIT (frontend) — DashboardSidebar nav labels.
// NavLink needs a Router in context, so we wrap in MemoryRouter.
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import DashboardSidebar from "../DashboardSidebar";

test("shows the three primary nav links plus Settings", () => {
  render(
    <MemoryRouter>
      <DashboardSidebar />
    </MemoryRouter>
  );

  for (const label of ["Main", "Learners", "Generate", "Settings"]) {
    expect(screen.getByText(label)).toBeInTheDocument();
  }
});
