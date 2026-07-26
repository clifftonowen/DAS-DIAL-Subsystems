// The shared MSW server for frontend integration tests.
//
// Tests add their own route handlers with `server.use(...)`; the defaults in
// handlers.js only cover routes several tests share. Lifecycle hooks
// (listen / resetHandlers / close) belong in each test file so unit tests, which
// mock at the module boundary instead, never start a server.
import { setupServer } from "msw/node";
import { handlers } from "./handlers";

export const server = setupServer(...handlers);
