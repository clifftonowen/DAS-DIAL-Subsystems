/**
 * Jest config for React component unit tests.
 *
 * Babel is configured inline here (not via a project-wide babel.config file) so
 * it applies ONLY to Jest and never interferes with Vite's own build pipeline.
 * `transform-import-meta` keeps files that reference `import.meta.env` (e.g.
 * src/lib/supabase.js) parseable — though component tests should still mock
 * `../lib/supabase` rather than load the real Supabase client.
 */
module.exports = {
  testEnvironment: "jsdom",
  setupFilesAfterEnv: ["<rootDir>/src/setupTests.js"],
  testMatch: ["<rootDir>/src/**/*.test.{js,jsx}"],
  moduleNameMapper: {
    // Tailwind/PostCSS classes -> proxy that returns the class name as-is.
    "\\.(css|less|scss|sass)$": "identity-obj-proxy",
    // Static asset imports -> a harmless string stub.
    "\\.(png|jpe?g|gif|svg|webp|avif)$": "<rootDir>/test/fileMock.cjs",
  },
  transform: {
    "^.+\\.(js|jsx)$": ["babel-jest", {
      presets: [
        ["@babel/preset-env", { targets: { node: "current" } }],
        ["@babel/preset-react", { runtime: "automatic" }],
      ],
      plugins: ["babel-plugin-transform-import-meta"],
    }],
  },
};
