import { expect } from "@playwright/test";

/**
 * Dismiss the API key overlay if it auto-opens on 403.
 * Waits a moment for the app to finish its initial API calls (which may
 * trigger the overlay via 403), then closes it if visible.
 */
export async function dismissApiKeyOverlay(page) {
  await page.waitForTimeout(1000);
  const overlay = page.locator("#apikey-overlay");
  if (await overlay.isVisible()) {
    // Use JavaScript to close it — force-adding hidden class avoids the
    // intercept issue where the overlay's aria-modal blocks clicks on the close button.
    await overlay.evaluate((el) => el.classList.add("hidden"));
    await expect(overlay).toBeHidden();
  }
}
