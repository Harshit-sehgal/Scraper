import { test, expect } from "@playwright/test";

// Helper: dismiss the apikey overlay if it auto-opens on 403.
async function dismissApiKeyOverlay(page) {
  await page.waitForTimeout(1000);
  const overlay = page.locator("#apikey-overlay");
  if (await overlay.isVisible().catch(() => false)) {
    await overlay.evaluate((el) => el.classList.add("hidden"));
    await expect(overlay).toBeHidden();
  }
}

test.describe("Recycle bin view", () => {
  test("navigates to recycle bin and shows the view", async ({ page }) => {
    await page.goto("/app/");
    await dismissApiKeyOverlay(page);
    await page.locator("#nav-recycle").click();
    await expect(page.locator("#view-recycle")).toBeVisible();
  });

  test("shows the empty state when no jobs are recycled", async ({ page }) => {
    await page.goto("/app/");
    await dismissApiKeyOverlay(page);
    await page.locator("#nav-recycle").click();
    await expect(page.locator("#view-recycle")).toBeVisible();
    // The empty state illustration should be visible when no jobs are deleted
    await expect(page.locator("#empty-recycle-state")).toBeVisible();
  });

  test("shows recycle bin header", async ({ page }) => {
    await page.goto("/app/");
    await dismissApiKeyOverlay(page);
    await page.locator("#nav-recycle").click();
    await expect(page.locator(".recycle-list-head")).toBeVisible();
  });

  test("recycle list container is present", async ({ page }) => {
    await page.goto("/app/");
    await dismissApiKeyOverlay(page);
    await page.locator("#nav-recycle").click();
    await expect(page.locator("#recycle-list")).toBeVisible();
  });

  test("recycle tab is active when viewing recycle bin", async ({ page }) => {
    await page.goto("/app/");
    await dismissApiKeyOverlay(page);
    await page.locator("#nav-recycle").click();
    // The recycle tab should be active
    await expect(page.locator("#nav-recycle")).toHaveClass(/active/);
  });

  test("navigating to recycle and back to jobs works", async ({ page }) => {
    await page.goto("/app/");
    await dismissApiKeyOverlay(page);
    // Go to recycle
    await page.locator("#nav-recycle").click();
    await expect(page.locator("#view-recycle")).toBeVisible();
    // Go back to jobs
    await page.locator("#nav-jobs").click();
    await expect(page.locator("#view-jobs")).toBeVisible();
  });
});
