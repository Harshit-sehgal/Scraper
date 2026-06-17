/**
 * Vitest tests for the Recent Activity panel.
 */
import { describe, it, expect, beforeEach, afterEach } from "vitest";

describe("recent-activity module", () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <ol id="recent-activity-list"></ol>
      <span id="recent-activity-refreshed-at"></span>
    `;
  });

  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("exports refreshRecentActivity, startRecentActivity, stopRecentActivity", async () => {
    const mod = await import("./recent-activity.js");
    expect(typeof mod.refreshRecentActivity).toBe("function");
    expect(typeof mod.startRecentActivity).toBe("function");
    expect(typeof mod.stopRecentActivity).toBe("function");
  });
});
