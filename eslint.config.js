import js from "@eslint/js";
import globals from "globals";

export default [
  // Base recommended rules
  js.configs.recommended,

  // Root-level frontend source files (app.js, dashboard, landing)
  {
    files: [
      "frontend/app.js",
      "frontend/dashboard/**/*.js",
      "frontend/landing/**/*.js",
    ],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: {
        ...globals.browser,
        ...globals.es2021,
      },
    },
    rules: {
      "no-unused-vars": ["warn", { argsIgnorePattern: "^_", varsIgnorePattern: "^_", caughtErrorsIgnorePattern: "^_" }],
      "no-undef": "error",
    },
  },

  // Frontend source files (browser ES modules under js/)
  {
    files: ["frontend/js/*.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: {
        ...globals.browser,
        ...globals.es2021,
      },
    },
    rules: {
      // Browser globals used intentionally
      "no-unused-vars": ["warn", { argsIgnorePattern: "^_", varsIgnorePattern: "^_", caughtErrorsIgnorePattern: "^_" }],
      "no-undef": "error",
    },
  },

  // Frontend test files — relax unused-vars for mocks/expect
  {
    files: ["frontend/js/*.test.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: {
        ...globals.browser,
        ...globals.es2021,
        ...globals.vitest,
        // jsdom-based tests use `global` to stub window-level globals
        global: "writable",
      },
    },
    rules: {
      "no-unused-vars": "off",
    },
  },

  // E2E configuration & support files (Node.js)
  {
    files: ["frontend/playwright.config.mjs", "frontend/e2e/global-setup.mjs"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: {
        ...globals.node,
      },
    },
    rules: {
      "no-undef": "off",
    },
  },

  // E2E test spec files (Node + Playwright)
  {
    files: ["frontend/e2e/*.spec.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: {
        ...globals.node,
      },
    },
    rules: {
      "no-unused-vars": "off",
      "no-undef": "off",
    },
  },

  // Ignore vendored / generated directories
  {
    ignores: [
      "frontend/dist/**",
      "frontend/dashboard/vendor/**",
      "frontend/fonts/**",
      "frontend/smoke/**",
      "node_modules/**",
      ".venv/**",
      "coverage_html/**",
    ],
  },
];
