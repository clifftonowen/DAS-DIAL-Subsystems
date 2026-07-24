// Adds custom matchers like toBeInTheDocument / toHaveTextContent to expect().
// Loaded before every test file via jest.config.cjs setupFilesAfterEnv.
import "@testing-library/jest-dom";

// jsdom doesn't define TextEncoder/TextDecoder, which react-router v7 needs.
import { TextEncoder, TextDecoder } from "util";
if (typeof globalThis.TextEncoder === "undefined") globalThis.TextEncoder = TextEncoder;
if (typeof globalThis.TextDecoder === "undefined") globalThis.TextDecoder = TextDecoder;
