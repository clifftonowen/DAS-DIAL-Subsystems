# Frontend UI tests (Jest + React Testing Library)

How to write and run unit tests for React components. Run everything from the
`frontend/` directory.

```bash
npm install                   # once — installs Jest, RTL, babel, etc.
npm test                      # run all frontend tests
npm run test:watch            # re-run on save while developing
npx jest ProfileMenu          # run one file by name filter
```

## Where tests live

Co-locate tests next to the components under `frontend/src/components/__tests__/`,
named `<Component>.test.jsx`. Jest auto-discovers anything matching
`src/**/*.test.{js,jsx}` (see `frontend/jest.config.cjs`) — no file to register in.

```
frontend/
  jest.config.cjs                 # jest + inline babel config (scoped to jest only)
  src/setupTests.js               # jest-dom matchers + TextEncoder polyfill (auto-loaded)
  test/fileMock.cjs               # stub returned for imported images/assets
  src/components/
    ProfileMenu.jsx
    __tests__/
      ProfileMenu.test.jsx        # <- your tests go here
```

## Add a new component test — step by step

Say you want to test `frontend/src/components/Button.jsx`.

1. **Create the file** at `frontend/src/components/__tests__/Button.test.jsx`.
   No registration needed — Jest picks it up automatically.

2. **Import** React Testing Library and the component:
   ```jsx
   import { render, screen } from "@testing-library/react";
   import userEvent from "@testing-library/user-event";
   import Button from "../Button";        // ../ = up out of __tests__ into components/
   ```

3. **Mock side-effecting imports** the component pulls in. If it imports
   `../lib/supabase` (or anything that hits the network / reads `import.meta.env`),
   stub it so the real client never loads. The `jest.mock` factory must be
   self-contained — put `jest.fn()` *inside* it, don't reference an outer variable:
   ```jsx
   jest.mock("../../lib/supabase", () => ({          // ../../ from __tests__ to src/lib
     supabase: { auth: { signOut: jest.fn() } },
   }));
   ```

4. **Wrap in a Router** if the component uses `NavLink` / `Link` / `useNavigate`
   / `useParams`:
   ```jsx
   import { MemoryRouter } from "react-router-dom";
   render(<MemoryRouter><Button to="/x">Go</Button></MemoryRouter>);
   ```

5. **Render, act, assert.** Query by visible text/role; `await` every `userEvent`
   interaction:
   ```jsx
   test("calls onClick when pressed", async () => {
     const onClick = jest.fn();
     render(<Button onClick={onClick}>Save</Button>);
     await userEvent.click(screen.getByText("Save"));
     expect(onClick).toHaveBeenCalledTimes(1);
   });
   ```

6. **Run it** from `frontend/`:
   ```bash
   npx jest Button               # just this file
   npm test                      # everything
   ```

## Full example

A complete test file — mirrors the shipped `src/components/__tests__/ProfileMenu.test.jsx`:

```jsx
// src/components/__tests__/ProfileMenu.test.jsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// Mock the Supabase client the component imports as "../lib/supabase".
jest.mock("../../lib/supabase", () => ({
  supabase: { auth: { signOut: jest.fn() } },
}));

import ProfileMenu from "../ProfileMenu";
import { supabase } from "../../lib/supabase";

const session = { user: { email: "owen@example.com" } };

test("opens the dropdown and shows the signed-in email", async () => {
  render(<ProfileMenu session={session} />);
  await userEvent.click(screen.getByText("My Profile"));
  expect(screen.getByText("owen@example.com")).toBeInTheDocument();
});

test("clicking Sign out calls supabase.auth.signOut", async () => {
  supabase.auth.signOut.mockClear();
  render(<ProfileMenu session={session} />);
  await userEvent.click(screen.getByText("My Profile"));
  await userEvent.click(screen.getByText("Sign out"));
  expect(supabase.auth.signOut).toHaveBeenCalledTimes(1);
});
```

## Already handled for you

No per-test setup needed for any of this (all via `jest.config.cjs` + `src/setupTests.js`):

- `.css` / Tailwind imports and image/asset imports are auto-stubbed.
- jest-dom matchers (`toBeInTheDocument`, `toHaveTextContent`, …) are loaded globally.
- A `TextEncoder` polyfill is in place so `react-router` works under jsdom.

## Common gotchas

- Import the component with `../Name` (out of `__tests__`), and mock lib modules with
  `../../lib/...`.
- An element that renders more than once (e.g. an avatar initial shown in both the
  trigger and the dropdown) needs `getAllByText`, not `getByText`.
- For anything that appears *after* an interaction, prefer `findBy*` or `waitFor`
  over `getBy*`.
- The `jest.mock` factory can't reference variables declared outside it (Jest hoists
  it); build the mock inline and, if you need the mock fn in assertions, import it
  back from the mocked module (as in the example above).

## Query cheatsheet

| Need | Use |
|------|-----|
| Visible text | `screen.getByText("Save")` |
| Text appearing after a click | `await screen.findByText("Done")` |
| Multiple matches | `screen.getAllByText(...)` |
| Form field by label | `screen.getByLabelText("Email")` |
| Button/link by role | `screen.getByRole("button", { name: "Log in" })` |
| Click / type | `await userEvent.click(el)` / `await userEvent.type(el, "hi")` |
