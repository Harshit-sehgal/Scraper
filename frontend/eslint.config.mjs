import globals from "globals";

export default [
  {
    ignores: ["dist/**", "dashboard/vendor/**", "node_modules/**"],
  },
  {
    files: ["**/*.js", "**/*.mjs"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: {
        ...globals.browser,
        ...globals.es2021,
      },
      parserOptions: {
        ecmaFeatures: { impliedStrict: true },
      },
    },
    rules: {
      "no-undef": "error",
      "no-unused-vars": ["error", { argsIgnorePattern: "^_", caughtErrors: "none" }],
    },
  },
  {
    files: ["build.mjs", "playwright.config.mjs", "vitest.config.js", "mocks/**/*.js", "e2e/**/*.mjs"],
    languageOptions: {
      globals: {
        ...globals.node,
        ...globals.es2021,
      },
    },
  },
  {
    files: ["**/*.test.js", "**/mocks/**"],
    languageOptions: {
      globals: {
        ...globals.vitest,
        ...globals.node,
        ...globals.browser,
        ...globals.es2021,
      },
    },
  },
];
