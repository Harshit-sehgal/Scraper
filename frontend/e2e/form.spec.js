import { test, expect } from "@playwright/test";

test.describe("New job form interaction", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/app/");
    // Navigate to the new job view
    await page.locator("#btn-create-new").click();
    await expect(page.locator("#view-new")).toBeVisible();
  });

  test("navigates to new job view and shows form elements", async ({ page }) => {
    // Core form elements should be visible
    await expect(page.locator("#inp-name")).toBeVisible();
    await expect(page.locator("#inp-intent")).toBeVisible();
    await expect(page.locator("#btn-suggest-schema")).toBeVisible();
    await expect(page.locator("#btn-add-field")).toBeVisible();
    await expect(page.locator("#btn-add-filter")).toBeVisible();
    await expect(page.locator("#btn-submit")).toBeVisible();
  });

  test("fills in job name and intent", async ({ page }) => {
    await page.locator("#inp-name").fill("Test Job");
    await expect(page.locator("#inp-name")).toHaveValue("Test Job");

    await page.locator("#inp-intent").fill("Find company contact information");
    await expect(page.locator("#inp-intent")).toHaveValue("Find company contact information");
  });

  test("adds a schema field and fills its name and description", async ({ page }) => {
    // Click add field button
    await page.locator("#btn-add-field").click();

    // A field row should appear
    const fieldRow = page.locator(".field-row").first();
    await expect(fieldRow).toBeVisible();

    // Fill in field name
    const nameInput = fieldRow.locator(".sf-name");
    await nameInput.fill("company_name");
    await expect(nameInput).toHaveValue("company_name");

    // Change field type
    const typeSelect = fieldRow.locator(".sf-type");
    await typeSelect.selectOption("email");
    await expect(typeSelect).toHaveValue("email");

    // Fill in description
    const descInput = fieldRow.locator(".sf-desc");
    await descInput.fill("The official company name");
    await expect(descInput).toHaveValue("The official company name");
  });

  test("adds multiple schema fields", async ({ page }) => {
    // initForm() starts with 1 field. Add 2 more for 3 total.
    await page.locator("#btn-add-field").click();
    await page.locator("#btn-add-field").click();

    // All 3 should be present (1 initial + 2 added)
    await expect(page.locator(".field-row")).toHaveCount(3);

    // Fill them with different names
    const names = ["company_name", "email", "phone"];
    const rows = page.locator(".field-row");
    for (let i = 0; i < names.length; i++) {
      await rows.nth(i).locator(".sf-name").fill(names[i]);
      await expect(rows.nth(i).locator(".sf-name")).toHaveValue(names[i]);
    }
  });

  test("removes a schema field via the X button", async ({ page }) => {
    // initForm() starts with 1 field. Add 1 more for 2 total.
    await page.locator("#btn-add-field").click();
    await expect(page.locator(".field-row")).toHaveCount(2);

    // Remove the first field
    await page.locator(".field-row").first().locator(".btn-x").click();
    await expect(page.locator(".field-row")).toHaveCount(1);
  });

  test("adds a filter and shows operator options", async ({ page }) => {
    // initForm() starts with 1 field. Fill its name for filter reference.
    await page.locator(".sf-name").first().fill("rating");

    // Add a filter
    await page.locator("#btn-add-filter").click();

    const filterRow = page.locator(".filter-row").first();
    await expect(filterRow).toBeVisible();

    // Operator select should have options
    const opSelect = filterRow.locator(".ff-op");
    await expect(opSelect).toBeVisible();
    await expect(opSelect.locator("option")).toHaveCount(15);
  });

  test("filter distance_within shows extra fields", async ({ page }) => {
    // initForm() starts with 1 field. Fill its name for filter reference.
    await page.locator(".sf-name").first().fill("distance");

    // Add a filter
    await page.locator("#btn-add-filter").click();

    // Change operator to distance_within
    const filterRow = page.locator(".filter-row").first();
    await filterRow.locator(".ff-op").selectOption("distance_within");

    // Distance extras should appear
    await expect(filterRow.locator(".ff-origin")).toBeVisible();
    await expect(filterRow.locator(".ff-unit")).toBeVisible();

    // Label should change
    await expect(filterRow.locator(".ff-value-group label")).toHaveText("Max km/mi");

    // Fill origin address
    await filterRow.locator(".ff-origin").fill("Los Angeles, CA");
    await expect(filterRow.locator(".ff-origin")).toHaveValue("Los Angeles, CA");
  });

  test("switches between manual and auto mode", async ({ page }) => {
    // Manual mode is default
    const manualToggle = page.locator("#mode-toggle .toggle[data-mode='manual']");
    const autoToggle = page.locator("#mode-toggle .toggle[data-mode='auto']");
    await expect(manualToggle).toHaveClass(/active/);
    await expect(page.locator("#section-manual")).toBeVisible();
    await expect(page.locator("#section-auto")).not.toBeVisible();

    // Switch to auto mode
    await autoToggle.click();
    await expect(autoToggle).toHaveClass(/active/);
    await expect(manualToggle).not.toHaveClass(/active/);
    await expect(page.locator("#section-auto")).toBeVisible();
    await expect(page.locator("#section-manual")).not.toBeVisible();

    // Switch back to manual
    await manualToggle.click();
    await expect(manualToggle).toHaveClass(/active/);
    await expect(page.locator("#section-manual")).toBeVisible();
    await expect(page.locator("#section-auto")).not.toBeVisible();
  });

  test("enters URLs in manual mode", async ({ page }) => {
    // Manual mode should show URLs textarea
    await expect(page.locator("#inp-urls")).toBeVisible();

    // Enter URLs
    const urls = "https://example.com\nhttps://test.org\nhttps://demo.com";
    await page.locator("#inp-urls").fill(urls);
    await expect(page.locator("#inp-urls")).toHaveValue(urls);
  });

  test("fills in auto mode fields", async ({ page }) => {
    // Switch to auto mode
    await page.locator("#mode-toggle .toggle[data-mode='auto']").click();

    // Fill auto mode fields
    await page.locator("#inp-topic").fill("restaurants in Chicago");
    await expect(page.locator("#inp-topic")).toHaveValue("restaurants in Chicago");

    await page.locator("#inp-location").fill("Chicago, IL");
    await expect(page.locator("#inp-location")).toHaveValue("Chicago, IL");

    await page.locator("#inp-domain").fill("yelp.com");
    await expect(page.locator("#inp-domain")).toHaveValue("yelp.com");
  });

  test("analyze URL section is present on the form", async ({ page }) => {
    // Scroll to the analyze section
    const analyzeSection = page.locator("#btn-analyze-url");
    await expect(analyzeSection).toBeVisible();

    // URL input for analysis should be visible
    await expect(page.locator("#inp-analyze-url")).toBeVisible();

    // Enter a URL to analyze (won't actually send due to API)
    await page.locator("#inp-analyze-url").fill("https://example.com");
    await expect(page.locator("#inp-analyze-url")).toHaveValue("https://example.com");
  });

  test("tab navigation persists when switching back to new job", async ({ page }) => {
    // Fill in some form data
    await page.locator("#inp-name").fill("Persistent Test");

    // Switch to jobs tab
    await page.locator("#tab-jobs").click();
    await expect(page.locator("#view-jobs")).toBeVisible();

    // Switch back to new job
    await page.locator("#tab-new").click();
    await expect(page.locator("#view-new")).toBeVisible();
  });
});
