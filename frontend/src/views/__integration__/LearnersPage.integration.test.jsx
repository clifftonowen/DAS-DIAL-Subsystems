// FRONTEND INTEGRATION (placeholder) — LearnersPage.
//
// Integration = several components + routing working together with the NETWORK
// mocked (via MSW), rendered in Jest/jsdom. Broader than a unit test (which
// mocks every collaborator), cheaper/faster than a Selenium system test.
//
// These are `test.todo` placeholders so `npm test` stays green with no new deps.
// To turn them into real tests, install MSW and follow ./README.md — then replace
// each `test.todo(...)` with a real `test(...)` body.
//
// Naming: *.integration.test.jsx keeps them distinct from unit tests while still
// being auto-discovered by jest.config.cjs (testMatch: src/**/*.test.{js,jsx}).

describe("LearnersPage (integration, MSW)", () => {
  test.todo("renders the learners fetched from the API");
  test.todo("filters the visible list as the user types in the search box");
  test.todo("navigates to the learner detail page when a card is clicked");
  test.todo("shows an error state when the learners request fails");
});
