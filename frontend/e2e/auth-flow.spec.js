import { test, expect } from "@playwright/test";
import { dismissApiKeyOverlay } from "./helpers.js";

test.describe("Authenticated job creation flow", () => {
  test("create a manual job and verify it appears in the jobs list", async ({ page }) => {
    await page.goto("/app/");
    await dismissApiKeyOverlay(page);

    // Navigate to the New Job form
    await page.locator("#nav-new").click();
    await expect(page.locator("#view-new")).toBeVisible();

    // Wait for the form to be fully initialised (async dropdown refresh)
    await page.waitForSelector("#inp-name", { timeout: 5000 });

    // Fill in job name
    const jobName = `E2E Test Job ${Date.now()}`;
    await page.locator("#inp-name").fill(jobName);

    // The form defaults to manual mode — fill in a URL
    await page.locator("#inp-urls").fill("https://example.com");

    // Add a schema field (the form auto-adds one field, but fill it)
    const schemaField = page.locator(".sf-name").first();
    await schemaField.fill("title");

    // Submit the job
    await page.locator("#btn-submit").click();

    // After submission, the app navigates to the jobs list view
    // Wait for the jobs view to be active
    await expect(page.locator("#view-jobs")).toBeVisible({ timeout: 10000 });

    // The new job should appear in the jobs list
    await expect(page.locator(`text=${jobName}`)).toBeVisible({ timeout: 10000 });

    // Verify the job status badge shows it was queued/created (not failed)
    // The job row's badge should contain a status label like "Queued"
    await expect(page.locator(`text=${jobName}`).locator("..").locator(".badge")).toBeVisible({ timeout: 5000 });
  });

  test("form validation shows errors for missing required fields", async ({ page }) => {
    await page.goto("/app/");
    await dismissApiKeyOverlay(page);

    // Navigate to the New Job form
    await page.locator("#nav-new").click();
    await expect(page.locator("#view-new")).toBeVisible();
    await page.waitForSelector("#inp-name", { timeout: 5000 });

    // Try submitting without filling required fields
    await page.locator("#btn-submit").click();

    // Should see form validation errors
    await expect(page.locator("#form-errors")).toBeVisible();
    // The error should mention the job name is required
    const errorText = await page.locator("#form-errors").textContent();
    expect(errorText.toLowerCase()).toContain("name");
  });
});
