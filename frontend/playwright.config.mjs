import { defineConfig, devices } from "@playwright/test";
import { resolve } from "node:path";

const storageStatePath = resolve("frontend/e2e/.auth/storage-state.json");
const shouldUseStorageState = Boolean(
  process.env.DATAFORGE_E2E_API_KEY || process.env.DATAFORGE_OPERATOR_API_KEY || process.env.DATAFORGE_API_KEY,
);

export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.mjs",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: "html",
  use: {
    baseURL: process.env.DATAFORGE_BASE_URL || "http://localhost:8000",
    storageState: shouldUseStorageState ? storageStatePath : undefined,
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
