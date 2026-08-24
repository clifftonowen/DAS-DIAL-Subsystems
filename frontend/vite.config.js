import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// The three VITE_* vars are inlined at BUILD time, not read at runtime, so a build that runs
// without them produces a bundle that looks fine and is broken in the browser. The two Supabase
// ones at least fail loudly — createClient(undefined, undefined) throws on load and the app
// white-screens. VITE_API_URL is the dangerous one: api.js falls back to http://localhost:8000,
// so a deployed bundle silently points every request at the visitor's own machine and every call
// dies as an opaque "Failed to fetch" with nothing in the console explaining why.
//
// loadEnv, not process.env: Vite reads .env files into its own config object and does NOT put
// them on process.env, so checking process.env alone would fail a local build that has a
// perfectly good frontend/.env. loadEnv with an empty prefix reads .env* the same way the build
// itself will, and it also picks up real process env vars — which is how CI and the Pages build
// supply these.
//
// Only enforced for `build`. `vite dev` is expected to run off the localhost fallback.
const REQUIRED = ["VITE_API_URL", "VITE_SUPABASE_URL", "VITE_SUPABASE_ANON_KEY"];

export default defineConfig(({ command, mode }) => {
  if (command === "build") {
    const env = loadEnv(mode, process.cwd(), "");
    const missing = REQUIRED.filter((k) => !env[k]);
    if (missing.length) {
      throw new Error(
        `Missing build-time env: ${missing.join(", ")}. These are inlined into the bundle, so ` +
          `building without them ships a broken app rather than failing at runtime. Set them in ` +
          `frontend/.env or in the host's build environment.`
      );
    }
  }
  return { plugins: [react()], server: { port: 5173 } };
});
