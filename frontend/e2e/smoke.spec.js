import { test, expect } from "@playwright/test";
import { dismissApiKeyOverlay } from "./helpers.js";

test.describe("Dashboard UI smoke tests", () => {
  test("page loads and shows the DataForge brand", async ({ page }) => {
    await page.goto("/app/");
    await dismissApiKeyOverlay(page);
    await expect(page.locator(".sidebar-brand-name")).toHaveText("DataForge");
  });

  test("sidebar nav items are visible", async ({ page }) => {
    await page.goto("/app/");
    await dismissApiKeyOverlay(page);
    await expect(page.locator("#nav-jobs")).toBeVisible();
    await expect(page.locator("#nav-new")).toBeVisible();
    await expect(page.locator("#nav-recycle")).toBeVisible();
    await expect(page.locator("#nav-dashboard")).toBeVisible();
  });

  test("clicking Quick Deploy navigates to new job view", async ({ page }) => {
    await page.goto("/app/");
    await dismissApiKeyOverlay(page);
    await page.locator(".sidebar-quick-deploy").click();
    await expect(page.locator("#view-new")).toBeVisible();
  });

  test("desktop shell uses sidebar-only chrome", async ({ page }) => {
    await page.goto("/app/");
    await dismissApiKeyOverlay(page);
    await expect(page.locator(".sidebar")).toBeVisible();
    await expect(page.locator(".topbar")).toBeHidden();
  });

  test("dashboard nav navigates to dashboard view", async ({ page }) => {
    await page.goto("/app/");
    await dismissApiKeyOverlay(page);
    await page.locator("#nav-dashboard").click();
    await expect(page.locator("#view-dashboard")).toBeVisible();
  });

  test("dashboard shows all panel containers", async ({ page }) => {
    await page.goto("/app/");
    await dismissApiKeyOverlay(page);
    await page.locator("#nav-dashboard").click();
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
    await dismissApiKeyOverlay(page);
    await page.locator("#nav-dashboard").click();
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
