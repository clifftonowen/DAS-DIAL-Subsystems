/**
 * Babel plugin: make Vite's `import.meta.env` work under Jest.
 *
 * Vite replaces `import.meta.env.FOO` at build time; Jest doesn't, and Node
 * refuses to even parse `import.meta` inside the CommonJS wrapper Jest compiles
 * to — so any test that loads a module reading `import.meta.env` (src/lib/api.js,
 * src/lib/supabase.js) dies with "Cannot use 'import.meta' outside a module".
 *
 * `babel-plugin-transform-import-meta` does NOT cover this: it only rewrites
 * `import.meta.url`, leaving `import.meta.env` untouched. That went unnoticed
 * because no test loaded those modules for real until the level-4 integration
 * tests in src/views/__integration__/ arrived.
 *
 * This rewrites `import.meta` to `{ env: process.env, url: __filename }`, so
 * `import.meta.env.VITE_API_URL` reads from `process.env` — the same lookup Vite
 * does, which means a test can set the var if it needs to. Unset, api.js falls
 * back to its default http://localhost:8000.
 */
module.exports = function transformImportMetaEnv({ types: t }) {
  return {
    name: "transform-import-meta-env",
    visitor: {
      MetaProperty(path) {
        path.replaceWith(
          t.objectExpression([
            t.objectProperty(
              t.identifier("env"),
              t.memberExpression(t.identifier("process"), t.identifier("env"))
            ),
            t.objectProperty(t.identifier("url"), t.identifier("__filename")),
          ])
        );
      },
    },
  };
};
