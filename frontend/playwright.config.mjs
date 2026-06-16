// Playwright configuration for the DataForge frontend E2E suite.
//
// Storage state path is anchored to this file's location
// (fileURLToPath(import.meta.url)) so the suite behaves identically whether
// invoked via `npx playwright test --config frontend/playwright.config.mjs`
// from the project root, or via `npm run test:e2e` (cwd = frontend/).

import { defineConfig, devices } from "@playwright/test";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const configDir = dirname(__filename);

const apiKey =
  process.env.DATAFORGE_E2E_API_KEY || process.env.DATAFORGE_OPERATOR_API_KEY || process.env.DATAFORGE_API_KEY || "";

const storageStatePath = resolve(configDir, "e2e/.auth/storage-state.json");

/** @type {import('@playwright/test').PlaywrightTestConfig} */
const config = defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? [["list"], ["html"]] : "list",
  use: {
    baseURL: process.env.DATAFORGE_BASE_URL || "http://localhost:8000",
    trace: "on-first-retry",
    ...(apiKey ? { storageState: storageStatePath } : {}),
  },
  // globalSetup path is resolved relative to this config file's directory by
  // Playwright, so "./e2e/global-setup.mjs" works regardless of cwd.
  globalSetup: "./e2e/global-setup.mjs",
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});

export default config;
