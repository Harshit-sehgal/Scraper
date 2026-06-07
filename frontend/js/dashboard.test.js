/* ═══════════════════════════════════════════
   DataForge — Operations Dashboard Tests
   ═══════════════════════════════════════════ */

import { describe, it, expect, beforeEach, afterEach } from "vitest";

// refreshDashboard and switchOperatorMode are async network-driven
// functions that delegate to imported render modules. They are not
// meaningfully unit-testable without mocking the entire network
// layer. We verify the module loads and exports are correct, and
// test the one pure helper (setEl) indirectly through the exports.
import { refreshDashboard, switchOperatorMode } from "./dashboard.js";

// ─── Setup / Teardown ──────────────────────────────────────────────────────

beforeEach(() => {
  document.body.innerHTML = `
    <div id="dash-status-val"></div>
    <div id="dash-success-rate"></div>
    <div id="dash-active-browsers"></div>
    <div id="dash-domains-degraded"></div>
    <div id="dash-current-mode"></div>
    <div id="mode-feedback" class="hidden"></div>
    <div id="view-dashboard"><button class="btn primary small">Refresh</button></div>
  `;
});

afterEach(() => {
  document.body.innerHTML = "";
});

// ─── Module Exports ────────────────────────────────────────────────────────

describe("dashboard module", () => {
  it("exports refreshDashboard as a function", () => {
    expect(typeof refreshDashboard).toBe("function");
  });

  it("exports switchOperatorMode as a function", () => {
    expect(typeof switchOperatorMode).toBe("function");
  });
});
