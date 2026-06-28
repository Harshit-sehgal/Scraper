import { test, expect } from "@playwright/test";
import { dismissApiKeyOverlay } from "./helpers.js";

test.describe("Auth profiles view", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/app/");
    await dismissApiKeyOverlay(page);
    await page.locator("#nav-auth-profiles").click();
  });

  test("shows the auth profiles view", async ({ page }) => {
    await expect(page.locator("#view-auth-profiles")).toBeVisible();
  });
});

test.describe("Scheduled monitoring view", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/app/");
    await dismissApiKeyOverlay(page);
    await page.locator("#nav-scheduled-monitoring").click();
  });

  test("shows the scheduled monitoring view", async ({ page }) => {
    await expect(page.locator("#view-scheduled-monitoring")).toBeVisible();
  });
});

test.describe("Invitations view", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/app/");
    await dismissApiKeyOverlay(page);
    await page.locator("#nav-invitations").click();
  });

  test("shows the invitations view", async ({ page }) => {
    await expect(page.locator("#view-invitations")).toBeVisible();
  });
});
