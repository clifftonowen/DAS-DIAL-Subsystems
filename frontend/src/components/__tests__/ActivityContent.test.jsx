// UNIT (frontend) — ActivityContent turns the model's Markdown into elements.
//
// The point of the component is that no raw ** or # reaches the screen, so most
// assertions check both the formatting AND the absence of the source syntax.

import { render, screen } from "@testing-library/react";
import ActivityContent from "../ActivityContent";

test("renders **bold** as an element, not literal asterisks", () => {
  const { container } = render(<ActivityContent text="**Objective:** blend sounds" />);

  expect(container.querySelector("strong")).toHaveTextContent("Objective:");
  expect(container.textContent).toContain("blend sounds");
  expect(container.textContent).not.toContain("*");
});

test("renders a heading without its hashes", () => {
  const { container } = render(<ActivityContent text="## Materials" />);

  expect(screen.getByText("Materials")).toBeInTheDocument();
  expect(container.textContent).not.toContain("#");
});

test("groups numbered lines into an ordered list", () => {
  const { container } = render(
    <ActivityContent text={"1. Clap the rhyme\n2. Say the onset\n3. Blend it back"} />
  );

  const items = container.querySelectorAll("ol li");
  expect(items).toHaveLength(3);
  expect(items[0]).toHaveTextContent("Clap the rhyme");
  expect(container.querySelector("ul")).toBeNull();
});

test("groups dashed lines into a bullet list", () => {
  const { container } = render(<ActivityContent text={"- picture cards\n- a whiteboard"} />);

  expect(container.querySelectorAll("ul li")).toHaveLength(2);
  expect(container.textContent).not.toContain("-");
});

test("a blank line separates paragraphs", () => {
  const { container } = render(<ActivityContent text={"First para.\n\nSecond para."} />);

  const paragraphs = [...container.querySelectorAll("p")];
  expect(paragraphs).toHaveLength(2);
  expect(paragraphs[0]).toHaveTextContent("First para.");
});

test("wrapped lines inside one paragraph are joined, not split", () => {
  const { container } = render(<ActivityContent text={"The learner\nblends the sounds."} />);

  expect(container.querySelectorAll("p")).toHaveLength(1);
  expect(container.textContent).toBe("The learner blends the sounds.");
});

test("handles a full activity: heading, bold labels and a numbered list", () => {
  const { container } = render(
    <ActivityContent
      text={"# Rhyme Time\n\n**Objective:** hear rhyme\n\nSteps\n\n1. Clap\n2. Say"}
    />
  );

  expect(screen.getByText("Rhyme Time")).toBeInTheDocument();
  expect(container.querySelector("strong")).toHaveTextContent("Objective:");
  expect(container.querySelectorAll("ol li")).toHaveLength(2);
  expect(container.textContent).not.toMatch(/[*#]/);
});

test("plain prose renders unchanged", () => {
  render(<ActivityContent text="Just a sentence." />);
  expect(screen.getByText("Just a sentence.")).toBeInTheDocument();
});

test("empty or missing text does not throw", () => {
  expect(() => render(<ActivityContent text="" />)).not.toThrow();
  expect(() => render(<ActivityContent />)).not.toThrow();
});
