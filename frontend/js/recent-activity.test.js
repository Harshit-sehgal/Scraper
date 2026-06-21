/* ═══════════════════════════════════════════
   DataForge — Recent Activity Smoke Tests
   ═══════════════════════════════════════════ */

import { describe, it, expect } from "vitest";

import { startRecentActivity, stopRecentActivity } from "./recent-activity.js";

describe("recent-activity module", () => {
  it("exports startRecentActivity as a function", () => {
    expect(typeof startRecentActivity).toBe("function");
  });

  it("exports stopRecentActivity as a function", () => {
    expect(typeof stopRecentActivity).toBe("function");
  });
});
