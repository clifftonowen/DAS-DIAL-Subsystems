/**
 * Jest config for React component + view tests.
 *
 * Babel is configured inline here (not via a project-wide babel.config file) so
 * it applies ONLY to Jest and never interferes with Vite's own build pipeline.
 * `test/babelPluginImportMeta.cjs` makes files that read `import.meta.env` (e.g.
 * src/lib/api.js, src/lib/supabase.js) loadable — though component *unit* tests
 * should still mock `../lib/supabase` rather than load the real Supabase client.
 *
 * testEnvironment is `jest-fixed-jsdom`, a thin wrapper over jsdom that keeps
 * Node's own web globals (fetch, Request/Response, streams, BroadcastChannel)
 * instead of deleting them. Plain `jsdom` strips those, which breaks MSW v2 — the
 * level-4 integration tests in src/views/__integration__/ need a real fetch to
 * intercept. Everything else behaves exactly like jsdom.
 */
module.exports = {
  testEnvironment: "jest-fixed-jsdom",
  setupFilesAfterEnv: ["<rootDir>/src/setupTests.js"],
  testMatch: ["<rootDir>/src/**/*.test.{js,jsx}"],
  moduleNameMapper: {
    // Tailwind/PostCSS classes -> proxy that returns the class name as-is.
    "\\.(css|less|scss|sass)$": "identity-obj-proxy",
    // Static asset imports -> a harmless string stub.
    "\\.(png|jpe?g|gif|svg|webp|avif)$": "<rootDir>/test/fileMock.cjs",
  },
  // MSW v2 and a few of its deps ship ESM only, and Jest skips node_modules when
  // transforming. Whitelist just those so they get compiled to CJS like our own
  // source; everything else in node_modules stays untouched (and fast).
  transformIgnorePatterns: [
    "/node_modules/(?!(msw|@mswjs|@open-draft|rettime|until-async|outvariant|strict-event-emitter|headers-polyfill|is-node-process)/)",
  ],
  transform: {
    "^.+\\.(js|jsx|mjs)$": ["babel-jest", {
      presets: [
        ["@babel/preset-env", { targets: { node: "current" } }],
        ["@babel/preset-react", { runtime: "automatic" }],
      ],
      // Rewrites `import.meta.env` (Vite) so Jest can load src/lib/api.js and
      // src/lib/supabase.js for real. Replaces babel-plugin-transform-import-meta,
      // which only ever handled `import.meta.url` — see the plugin's own comment.
      // Resolved here, not written as "<rootDir>/...": Jest interpolates rootDir
      // in its own path options but not inside a transformer's config.
      plugins: [require.resolve("./test/babelPluginImportMeta.cjs")],
    }],
  },
};
