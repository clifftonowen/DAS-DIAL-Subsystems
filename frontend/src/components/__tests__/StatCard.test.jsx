// UNIT (frontend) — StatCard renders its text props (icon-free after cleanup).
import { render, screen } from "@testing-library/react";
import StatCard from "../StatCard";

test("renders title, subtitle and trailing content", () => {
  render(
    <StatCard
      title="Flagged Activities"
      subtitle="2 activities need your review"
      trailing={<span>2</span>}
    />
  );

  expect(screen.getByText("Flagged Activities")).toBeInTheDocument();
  expect(screen.getByText("2 activities need your review")).toBeInTheDocument();
  expect(screen.getByText("2")).toBeInTheDocument();
});
