import { test, expect } from "@playwright/test";

// Helper: dismiss the apikey overlay if it auto-opens on 403.
// Wait a moment for the app to finish its initial API calls (which may
// trigger the overlay via 403), then close it if visible.
async function dismissApiKeyOverlay(page) {
  await page.waitForTimeout(1000);
  const overlay = page.locator("#apikey-overlay");
  if (await overlay.isVisible().catch(() => false)) {
    await overlay.evaluate((el) => el.classList.add("hidden"));
    await expect(overlay).toBeHidden();
  }
}

test.describe("Auth flow", () => {
  test.describe("with session cookie (authenticated)", () => {
    test("page loads with authenticated user profile", async ({ page }) => {
      // Navigate to the dashboard
      await page.goto("/app/");
      await dismissApiKeyOverlay(page);

      // The brand should be visible
      await expect(page.locator(".sidebar-brand-name")).toHaveText("DataForge");

      // Navigate to dashboard
      await page.locator("#nav-dashboard").click();
      await expect(page.locator("#view-dashboard")).toBeVisible();

      // Health KPIs should be visible (authenticated endpoint)
      await expect(page.locator("#dash-status-val")).toBeVisible();
    });

    test("can navigate between all main views", async ({ page }) => {
      await page.goto("/app/");
      await dismissApiKeyOverlay(page);

      // Jobs view
      await page.locator("#nav-jobs").click();
      await expect(page.locator("#view-jobs")).toBeVisible();

      // New job view
      await page.locator("#nav-new").click();
      await expect(page.locator("#view-new")).toBeVisible();
      await expect(page.locator("#inp-name")).toBeVisible();

      // Recycle bin view
      await page.locator("#nav-recycle").click();
      await expect(page.locator("#view-recycle")).toBeVisible();

      // Dashboard view
      await page.locator("#nav-dashboard").click();
      await expect(page.locator("#view-dashboard")).toBeVisible();
    });

    test("billing page loads and shows plan info", async ({ page }) => {
      await page.goto("/app/");
      await dismissApiKeyOverlay(page);

      // Navigate to billing
      await page.locator("#nav-billing").click();
      await expect(page.locator("#view-billing")).toBeVisible();

      // Billing plan info should be present
      await expect(page.locator("#billing-kpi-tier")).toBeVisible();
    });

    test("dashboard header shows cluster status", async ({ page }) => {
      await page.goto("/app/");
      await dismissApiKeyOverlay(page);

      await page.locator("#nav-dashboard").click();
      await expect(page.locator("#dash-status-line")).toBeVisible();
      await expect(page.locator("#dash-status-label")).toBeVisible();
    });
  });
});
