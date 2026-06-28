import { test, expect } from "@playwright/test";
import { dismissApiKeyOverlay } from "./helpers.js";

test.describe("Jobs list view", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/app/");
    await dismissApiKeyOverlay(page);
    await page.locator("#nav-jobs").click();
  });

  test("shows the jobs view", async ({ page }) => {
    await expect(page.locator("#view-jobs")).toBeVisible();
  });

  test("has a create job button", async ({ page }) => {
    await expect(page.locator("#btn-create-new")).toBeVisible();
  });

  test("clicking create job navigates to new job view", async ({ page }) => {
    await page.locator("#btn-create-new").click();
    await expect(page.locator("#view-new")).toBeVisible();
  });

  test("jobs table has header columns", async ({ page }) => {
    const table = page.locator("#jobs-table");
    await expect(table).toBeVisible();
    await expect(table.locator("th").first()).toBeVisible();
  });

  test("shows empty state when no jobs exist", async ({ page }) => {
    await expect(page.locator("#empty-state")).toBeVisible();
  });

  test("has search input and status filter", async ({ page }) => {
    await expect(page.locator("#jobs-search")).toBeVisible();
    await expect(page.locator("#jobs-status-filter")).toBeVisible();
  });

  test("shows pagination footer", async ({ page }) => {
    await expect(page.locator("#jobs-pagination-range")).toBeVisible();
  });
});

test.describe("API Keys view", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/app/");
    await dismissApiKeyOverlay(page);
    await page.locator("#nav-api-keys").click();
  });

  test("shows the API keys view", async ({ page }) => {
    await expect(page.locator("#view-api-keys")).toBeVisible();
  });

  test("has a generate key button", async ({ page }) => {
    await expect(page.locator("#btn-generate-key")).toBeVisible();
  });

  test("shows the API key status badge", async ({ page }) => {
    await expect(page.locator("#api-key-status")).toBeVisible();
  });
});

test.describe("Billing view", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/app/");
    await dismissApiKeyOverlay(page);
    await page.locator("#nav-billing").click();
  });

  test("shows the billing view", async ({ page }) => {
    await expect(page.locator("#view-billing")).toBeVisible();
  });

  test("shows plan tier KPI", async ({ page }) => {
    await expect(page.locator("#billing-kpi-tier")).toBeVisible();
  });

  test("shows usage meters", async ({ page }) => {
    await expect(page.locator("#billing-kpi-jobs")).toBeVisible();
  });

  test("has a refresh button", async ({ page }) => {
    await expect(page.locator("#btn-refresh-billing")).toBeVisible();
  });
});

test.describe("Audit view", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/app/");
    await dismissApiKeyOverlay(page);
    await page.locator("#nav-audit").click();
  });

  test("shows the audit view", async ({ page }) => {
    await expect(page.locator("#view-audit")).toBeVisible();
  });

  test("has category filter", async ({ page }) => {
    await expect(page.locator("#audit-category-filter")).toBeVisible();
  });

  test("has a refresh button", async ({ page }) => {
    await expect(page.locator("#btn-refresh-audit")).toBeVisible();
  });
});

test.describe("Retention view", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/app/");
    await dismissApiKeyOverlay(page);
    await page.locator("#nav-retention").click();
  });

  test("shows the retention view", async ({ page }) => {
    await expect(page.locator("#view-retention")).toBeVisible();
  });

  test("has a sync state button", async ({ page }) => {
    await expect(page.locator("#btn-refresh-retention")).toBeVisible();
  });
});

test.describe("Settings view", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/app/");
    await dismissApiKeyOverlay(page);
    await page.locator("#nav-settings").click();
  });

  test("shows the settings view", async ({ page }) => {
    await expect(page.locator("#view-settings")).toBeVisible();
  });

  test("shows the settings bento grid", async ({ page }) => {
    await expect(page.locator(".settings-bento-grid")).toBeVisible();
  });
});

test.describe("Workflows view", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/app/");
    await dismissApiKeyOverlay(page);
    await page.locator("#nav-workflows").click();
  });

  test("shows the workflows view", async ({ page }) => {
    await expect(page.locator("#view-workflows")).toBeVisible();
  });

  test("shows workflow KPIs", async ({ page }) => {
    await expect(page.locator("#workflows-kpi-row")).toBeVisible();
  });

  test("shows empty state when no workflows exist", async ({ page }) => {
    await expect(page.locator("#workflows-empty-state")).toBeVisible();
  });

  test("shows detail pane empty state", async ({ page }) => {
    await expect(page.locator("#workflows-detail-empty")).toBeVisible();
  });

  test("has create new job button", async ({ page }) => {
    await expect(page.locator("#btn-workflows-create-new")).toBeVisible();
  });
});
