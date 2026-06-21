/* ═══════════════════════════════════════════
   DataForge — Governance Smoke Tests
   ═══════════════════════════════════════════ */

import { describe, it, expect, beforeEach, afterEach } from "vitest";

import { renderGovernance } from "./governance.js";

beforeEach(() => {
  document.body.innerHTML = `<div id="dash-governance"></div>`;
});

afterEach(() => {
  document.body.innerHTML = "";
});

describe("governance module", () => {
  it("exports renderGovernance as a function", () => {
    expect(typeof renderGovernance).toBe("function");
  });

  it("renders governance metrics grid with data", () => {
    renderGovernance({
      active_mode: "production",
      resources: { proxy_health: 0.95 },
      browser: { active_contexts: 5, total_contexts: 10 },
      governor: { token_spend_dollars: 1.5, queue_sheds: 3, browser_prunes: 1 },
    });
    const el = document.getElementById("dash-governance");
    expect(el?.innerHTML).toContain("production");
    expect(el?.innerHTML).toContain("5");
    expect(el?.innerHTML).toContain("95%");
  });
});
