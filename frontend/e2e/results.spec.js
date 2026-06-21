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

test.describe("Results detail view", () => {
  test("shows empty state text when no job is selected", async ({ page }) => {
    await page.goto("/app/");
    await dismissApiKeyOverlay(page);
    // The empty state says "Select a job to view results"
    await expect(page.locator("#res-tbody")).toContainText("Select a job to view results");
  });

  test("results view has export buttons hidden by default", async ({ page }) => {
    await page.goto("/app/");
    await dismissApiKeyOverlay(page);
    // Export group starts hidden (display: none)
    await expect(page.locator("#export-group")).toBeHidden();
  });

  test("results view has progress bar hidden by default", async ({ page }) => {
    await page.goto("/app/");
    await dismissApiKeyOverlay(page);
    await expect(page.locator("#res-progress-wrap")).toBeHidden();
  });

  test("results view has search filter input", async ({ page }) => {
    await page.goto("/app/");
    await dismissApiKeyOverlay(page);
    // Elements inside #view-results are attached to DOM even when the
    // view is not active (CSS hides non-active views with display: none).
    await expect(page.locator("#inp-result-search")).toBeAttached();
    await expect(page.locator("#inp-result-search")).toHaveAttribute("placeholder", /Filter rows/);
  });

  test("results view has scrollbar controls", async ({ page }) => {
    await page.goto("/app/");
    await dismissApiKeyOverlay(page);
    const scrollbar = page.locator("#results-scrollbar");
    // Scrollbar is inside #view-results which is not active by default.
    await expect(scrollbar).toBeAttached();
    await expect(scrollbar.locator("#results-scroll-slider")).toBeAttached();
    await expect(scrollbar.locator("#results-scroll-pos")).toHaveText("0%");
  });

  test("results view has all export buttons present", async ({ page }) => {
    await page.goto("/app/");
    await dismissApiKeyOverlay(page);
    // Export buttons are inside #view-results (non-active view), so
    // they are attached to DOM but not visible (CSS display: none).
    await expect(page.locator("#btn-csv")).toBeAttached();
    await expect(page.locator("#btn-json")).toBeAttached();
    await expect(page.locator("#btn-excel")).toBeAttached();
    await expect(page.locator("#btn-reclean")).toBeAttached();
  });

  test("results table structure is present", async ({ page }) => {
    await page.goto("/app/");
    await dismissApiKeyOverlay(page);
    // Table elements are inside the non-active #view-results.
    await expect(page.locator("#res-table")).toBeAttached();
    await expect(page.locator("#res-thead")).toBeAttached();
    await expect(page.locator("#res-tbody")).toBeAttached();
  });

  test("AI insight, logs, and quality panels are hidden by default", async ({ page }) => {
    await page.goto("/app/");
    await dismissApiKeyOverlay(page);
    await expect(page.locator("#ai-insight-panel")).toBeHidden();
    await expect(page.locator("#logs-panel")).toBeHidden();
    await expect(page.locator("#quality-panel")).toBeHidden();
  });
});
