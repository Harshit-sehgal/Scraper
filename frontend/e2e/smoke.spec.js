import { test, expect } from "@playwright/test";

test.describe("Dashboard UI smoke tests", () => {
  test("page loads and shows the DataForge brand", async ({ page }) => {
    await page.goto("/app/");
    await expect(page.locator(".brand")).toHaveText("DataForge Studio");
  });

  test("tabs are visible", async ({ page }) => {
    await page.goto("/app/");
    await expect(page.locator("#tab-jobs")).toBeVisible();
    await expect(page.locator("#tab-new")).toBeVisible();
    await expect(page.locator("#tab-recycle")).toBeVisible();
    await expect(page.locator("#tab-dashboard")).toBeVisible();
  });

  test("clicking Create Job navigates to new job view", async ({ page }) => {
    await page.goto("/app/");
    await page.locator("#btn-create-new").click();
    await expect(page.locator("#view-new")).toBeVisible();
  });

  test("theme toggle works", async ({ page }) => {
    await page.goto("/app/");
    const toggle = page.locator("#btn-theme-toggle");
    await toggle.click();
    // After toggle we should have a toast notification
    await expect(page.locator(".toast")).toBeVisible();
  });
});
