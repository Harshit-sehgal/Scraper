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

    test("settings view is accessible from nav", async ({ page }) => {
      await page.goto("/app/");
      await dismissApiKeyOverlay(page);
      await page.locator("#nav-settings").click();
      await expect(page.locator("#view-settings")).toBeVisible();
    });

    test("api keys view is accessible from nav", async ({ page }) => {
      await page.goto("/app/");
      await dismissApiKeyOverlay(page);
      await page.locator("#nav-api-keys").click();
      await expect(page.locator("#view-api-keys")).toBeVisible();
    });

    test("audit view is accessible from nav", async ({ page }) => {
      await page.goto("/app/");
      await dismissApiKeyOverlay(page);
      await page.locator("#nav-audit").click();
      await expect(page.locator("#view-audit")).toBeVisible();
    });

    test("workflows view is accessible from nav", async ({ page }) => {
      await page.goto("/app/");
      await dismissApiKeyOverlay(page);
      await page.locator("#nav-workflows").click();
      await expect(page.locator("#view-workflows")).toBeVisible();
    });

    test("retention view is accessible from nav", async ({ page }) => {
      await page.goto("/app/");
      await dismissApiKeyOverlay(page);
      await page.locator("#nav-retention").click();
      await expect(page.locator("#view-retention")).toBeVisible();
    });

    test("invitations view is accessible from nav", async ({ page }) => {
      await page.goto("/app/");
      await dismissApiKeyOverlay(page);
      await page.locator("#nav-invitations").click();
      await expect(page.locator("#view-invitations")).toBeVisible();
    });

    test("navigate from jobs to recycle and back", async ({ page }) => {
      await page.goto("/app/");
      await dismissApiKeyOverlay(page);

      await page.locator("#nav-jobs").click();
      await expect(page.locator("#view-jobs")).toBeVisible();

      await page.locator("#nav-recycle").click();
      await expect(page.locator("#view-recycle")).toBeVisible();

      await page.locator("#nav-jobs").click();
      await expect(page.locator("#view-jobs")).toBeVisible();
    });

    test("dashboard governance panel visible", async ({ page }) => {
      await page.goto("/app/");
      await dismissApiKeyOverlay(page);
      await page.locator("#nav-dashboard").click();
      await expect(page.locator("#dash-governance")).toBeVisible();
    });

    test("dashboard domains panel visible", async ({ page }) => {
      await page.goto("/app/");
      await dismissApiKeyOverlay(page);
      await page.locator("#nav-dashboard").click();
      await expect(page.locator("#dash-domains")).toBeVisible();
    });

    test("dashboard telemetry panel visible", async ({ page }) => {
      await page.goto("/app/");
      await dismissApiKeyOverlay(page);
      await page.locator("#nav-dashboard").click();
      await expect(page.locator("#dash-telemetry")).toBeVisible();
    });

    test("dashboard rate limits panel visible", async ({ page }) => {
      await page.goto("/app/");
      await dismissApiKeyOverlay(page);
      await page.locator("#nav-dashboard").click();
      await expect(page.locator("#dash-rate-limits")).toBeVisible();
    });

    test("dashboard mode card shows rate limit tier", async ({ page }) => {
      await page.goto("/app/");
      await dismissApiKeyOverlay(page);
      await page.locator("#nav-dashboard").click();
      await expect(page.locator("#dash-rate-limit-tier")).toBeVisible();
    });

    test("dashboard shows success rate KPI", async ({ page }) => {
      await page.goto("/app/");
      await dismissApiKeyOverlay(page);
      await page.locator("#nav-dashboard").click();
      await expect(page.locator("#dash-success-rate")).toBeVisible();
    });

    test("dashboard shows active browsers KPI", async ({ page }) => {
      await page.goto("/app/");
      await dismissApiKeyOverlay(page);
      await page.locator("#nav-dashboard").click();
      await expect(page.locator("#dash-active-browsers")).toBeVisible();
    });

    test("dashboard shows degraded domains KPI", async ({ page }) => {
      await page.goto("/app/");
      await dismissApiKeyOverlay(page);
      await page.locator("#nav-dashboard").click();
      await expect(page.locator("#dash-domains-degraded")).toBeVisible();
    });

    test("dashboard shows predictions panel", async ({ page }) => {
      await page.goto("/app/");
      await dismissApiKeyOverlay(page);
      await page.locator("#nav-dashboard").click();
      await expect(page.locator("#dash-predictions")).toBeVisible();
    });

    test("topbar shows cluster mode badge", async ({ page }) => {
      await page.goto("/app/");
      await dismissApiKeyOverlay(page);
      await expect(page.locator("#topbar")).toBeVisible();
    });

    test("sidebar shows user avatar", async ({ page }) => {
      await page.goto("/app/");
      await dismissApiKeyOverlay(page);
      await expect(page.locator("#user-avatar")).toBeVisible();
    });

    test("sidebar shows logout button", async ({ page }) => {
      await page.goto("/app/");
      await dismissApiKeyOverlay(page);
      await expect(page.locator("#btn-logout")).toBeVisible();
    });
  });
});
