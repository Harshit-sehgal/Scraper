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

  test("dashboard tab navigates to dashboard view", async ({ page }) => {
    await page.goto("/app/");
    await page.locator("#tab-dashboard").click();
    await expect(page.locator("#view-dashboard")).toBeVisible();
  });

  test("dashboard shows all panel containers", async ({ page }) => {
    await page.goto("/app/");
    await page.locator("#tab-dashboard").click();
    await expect(page.locator("#view-dashboard")).toBeVisible();

    // All panel containers are present in the DOM (show "Loading..." initially)
    await expect(page.locator("#dash-governance")).toBeVisible();
    await expect(page.locator("#dash-domains")).toBeVisible();
    await expect(page.locator("#dash-predictions")).toBeVisible();
    await expect(page.locator("#dash-telemetry")).toBeVisible();
    await expect(page.locator("#dash-rate-limits")).toBeVisible();
  });

  test("dashboard shows operator mode card and health KPIs", async ({ page }) => {
    await page.goto("/app/");
    await page.locator("#tab-dashboard").click();
    await expect(page.locator("#view-dashboard")).toBeVisible();

    // Mode card elements
    await expect(page.locator("#dash-current-mode")).toBeVisible();
    await expect(page.locator("#dash-systemic-risk")).toBeVisible();
    await expect(page.locator("#dash-rate-limit-tier")).toBeVisible();

    // Health KPI row
    await expect(page.locator("#dash-status-val")).toBeVisible();
    await expect(page.locator("#dash-success-rate")).toBeVisible();
    await expect(page.locator("#dash-active-browsers")).toBeVisible();
    await expect(page.locator("#dash-domains-degraded")).toBeVisible();

    // Mode switcher buttons
    await expect(page.locator(".mode-btn").first()).toBeVisible();
  });
});
