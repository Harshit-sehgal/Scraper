import { test, expect } from "@playwright/test";

// Helper: dismiss the apikey overlay if it auto-opens on 403.
// Wait a moment for the app to finish its initial API calls (which may
// trigger the overlay via 403), then close it if visible.
async function dismissApiKeyOverlay(page) {
  // Give the app time to make initial API calls and potentially show the overlay
  await page.waitForTimeout(1000);
  const overlay = page.locator("#apikey-overlay");
  if (await overlay.isVisible()) {
    // Use JavaScript to close it — force-adding hidden class avoids the
    // intercept issue where the overlay's aria-modal blocks clicks on the close button.
    await overlay.evaluate((el) => el.classList.add("hidden"));
    await expect(overlay).toBeHidden();
  }
}

test.describe("Dashboard UI smoke tests", () => {
  test("page loads and shows the DataForge brand", async ({ page }) => {
    await page.goto("/app/");
    await dismissApiKeyOverlay(page);
    await expect(page.locator(".brand-name")).toHaveText("DataForge");
  });

  test("sidebar nav items are visible", async ({ page }) => {
    await page.goto("/app/");
    await dismissApiKeyOverlay(page);
    await expect(page.locator("#nav-jobs")).toBeVisible();
    await expect(page.locator("#nav-new")).toBeVisible();
    await expect(page.locator("#nav-recycle")).toBeVisible();
    await expect(page.locator("#nav-dashboard")).toBeVisible();
  });

  test("clicking Create Job navigates to new job view", async ({ page }) => {
    await page.goto("/app/");
    await dismissApiKeyOverlay(page);
    await page.locator("#btn-create-new").click();
    await expect(page.locator("#view-new")).toBeVisible();
  });

  test("theme toggle works", async ({ page }) => {
    await page.goto("/app/");
    await dismissApiKeyOverlay(page);
    const toggle = page.locator("#btn-theme-toggle");
    await toggle.click();
    // After toggle we should have a toast notification
    await expect(page.locator(".toast")).toBeVisible();
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
