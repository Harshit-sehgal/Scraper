/* ═══════════════════════════════════════════
   DataForge — Governance Rendering Tests
   ═══════════════════════════════════════════ */

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { renderGovernance } from "./governance.js";

/** @type {import("jsdom").JSDOM} */
let dom;

/**
 * Set up the DOM elements that renderGovernance targets.
 */
function setupDOM() {
  const container = document.createElement("div");
  container.id = "dash-governance";
  container.innerHTML = '<div class="dash-loading">Loading...</div>';
  document.body.appendChild(container);
}

beforeEach(() => {
  document.body.innerHTML = "";
  setupDOM();
});

afterEach(() => {
  document.body.innerHTML = "";
});

const GOVERNANCE_DATA = {
  active_mode: "autonomous",
  resources: {
    proxy_health: 0.95,
  },
  browser: {
    active_contexts: 3,
    total_contexts: 5,
  },
  governor: {
    token_spend_dollars: 0.42,
    queue_sheds: 2,
    browser_prunes: 1,
  },
};

// ─── Basic Rendering ───

describe("renderGovernance", () => {
  it("renders active mode value", () => {
    renderGovernance(GOVERNANCE_DATA);
    const el = document.getElementById("dash-governance");
    expect(el.innerHTML).toContain("autonomous");
  });

  it("renders browser counts as active/total", () => {
    renderGovernance(GOVERNANCE_DATA);
    const el = document.getElementById("dash-governance");
    expect(el.innerHTML).toContain("3 / 5");
  });

  it("renders proxy health as percentage", () => {
    renderGovernance(GOVERNANCE_DATA);
    const el = document.getElementById("dash-governance");
    expect(el.innerHTML).toContain("95%");
  });

  it("renders token spend with dollar sign", () => {
    renderGovernance(GOVERNANCE_DATA);
    const el = document.getElementById("dash-governance");
    expect(el.innerHTML).toContain("$0.420");
  });

  it("renders queue sheds", () => {
    renderGovernance(GOVERNANCE_DATA);
    const el = document.getElementById("dash-governance");
    expect(el.innerHTML).toContain(">2<");
  });

  it("renders browser prunes", () => {
    renderGovernance(GOVERNANCE_DATA);
    const el = document.getElementById("dash-governance");
    expect(el.innerHTML).toContain(">1<");
  });

  it("renders 6 metric cards", () => {
    renderGovernance(GOVERNANCE_DATA);
    const el = document.getElementById("dash-governance");
    const cards = el.querySelectorAll(".dash-metric");
    expect(cards.length).toBe(6);
  });

  // ─── Edge Cases ───

  it("does not crash when container is missing", () => {
    document.body.innerHTML = "";
    expect(() => renderGovernance(GOVERNANCE_DATA)).not.toThrow();
  });

  it("does not crash on null data", () => {
    expect(() => renderGovernance(null)).not.toThrow();
  });

  it("does not crash on undefined data", () => {
    expect(() => renderGovernance(undefined)).not.toThrow();
  });

  it("handles missing sub-objects gracefully", () => {
    renderGovernance({});
    const el = document.getElementById("dash-governance");
    // Should render with defaults (em dashes, zeros)
    expect(el.innerHTML).toContain("$0.000");
    expect(el.innerHTML).toContain("\u2014 / \u2014");
  });

  it("escapes HTML in mode value", () => {
    renderGovernance({
      active_mode: '<script>alert("xss")</script>',
      resources: {},
      browser: {},
      governor: {},
    });
    const el = document.getElementById("dash-governance");
    expect(el.innerHTML).toContain("&lt;script&gt;");
    expect(el.innerHTML).not.toContain("<script>");
  });

  it("handles all zero numeric values", () => {
    renderGovernance({
      active_mode: "manual",
      resources: { proxy_health: 0 },
      browser: { active_contexts: 0, total_contexts: 0 },
      governor: { token_spend_dollars: 0, queue_sheds: 0, browser_prunes: 0 },
    });
    const el = document.getElementById("dash-governance");
    expect(el.innerHTML).toContain("$0.000");
    expect(el.innerHTML).toContain("0%");
    expect(el.innerHTML).toContain("0 / 0");
  });

  it("handles very large proxy health values", () => {
    renderGovernance({
      active_mode: "auto",
      resources: { proxy_health: 999 },
      browser: { active_contexts: 0, total_contexts: 0 },
      governor: {},
    });
    const el = document.getElementById("dash-governance");
    // 999 * 100 = 99900%
    expect(el.innerHTML).toContain("99900%");
  });
});
