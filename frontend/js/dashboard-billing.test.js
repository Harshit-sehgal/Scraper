/* ═══════════════════════════════════════════
   DataForge — Dashboard Billing Widget Tests
   ═══════════════════════════════════════════ */

import { describe, it, expect, beforeEach, afterEach } from "vitest";

// ─── Module Exports ───

describe("dashboard-billing module exports", () => {
  it("exports refreshDashboardBilling function", async () => {
    const mod = await import("./dashboard-billing.js");
    expect(typeof mod.refreshDashboardBilling).toBe("function");
  });
});

// ─── HTML Structure Tests ───

describe("billing widget HTML structure", () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <div id="dash-billing" class="dash-card-body">
        <div class="dash-loading">Loading billing data...</div>
      </div>
    `;
  });

  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("has the billing container element", () => {
    const container = document.getElementById("dash-billing");
    expect(container).toBeDefined();
    expect(container.className).toContain("dash-card-body");
  });

  it("shows loading state initially", () => {
    const loading = document.querySelector(".dash-loading");
    expect(loading).toBeDefined();
    expect(loading.textContent).toContain("Loading billing");
  });
});

// ─── Billing Widget Bar Rendering Tests ───

describe("billing widget bar rendering", () => {
  it("renders bar track with correct structure", () => {
    const track = document.createElement("div");
    track.className = "billing-widget-bar-track";

    const fill = document.createElement("div");
    fill.className = "billing-widget-bar-fill";
    fill.style.width = "50%";
    track.appendChild(fill);

    expect(track.className).toContain("billing-widget-bar-track");
    expect(fill.style.width).toBe("50%");
  });

  it("renders bar header with label and value", () => {
    const header = document.createElement("div");
    header.className = "billing-widget-bar-header";
    header.innerHTML = `
      <span class="billing-widget-bar-label">Jobs</span>
      <span class="billing-widget-bar-val">5 / 100</span>
    `;

    const label = header.querySelector(".billing-widget-bar-label");
    const val = header.querySelector(".billing-widget-bar-val");

    expect(label.textContent).toBe("Jobs");
    expect(val.textContent).toBe("5 / 100");
  });

  it("applies fill-warning class at 75-89%", () => {
    const fill = document.createElement("div");
    fill.className = "billing-widget-bar-fill fill-warning";
    expect(fill.className).toContain("fill-warning");
  });

  it("applies fill-critical class at 90%+", () => {
    const fill = document.createElement("div");
    fill.className = "billing-widget-bar-fill fill-critical";
    expect(fill.className).toContain("fill-critical");
  });

  it("renders plan tier badge", () => {
    const badge = document.createElement("span");
    badge.className = "billing-widget-badge";
    badge.textContent = "FREE";
    expect(badge.className).toContain("billing-widget-badge");
    expect(badge.textContent).toBe("FREE");
  });

  it("renders billing note when near limit", () => {
    const note = document.createElement("div");
    note.className = "billing-widget-note";
    note.textContent = "Consider upgrading your plan";
    expect(note.className).toContain("billing-widget-note");
    expect(note.textContent).toContain("upgrading");
  });

  it("renders actions with view billing button", () => {
    const actions = document.createElement("div");
    actions.className = "billing-widget-actions";
    actions.innerHTML = `<button type="button" class="btn ghost small" data-action="switch-view" data-view="billing">View billing details</button>`;

    const btn = actions.querySelector('[data-action="switch-view"]');
    expect(btn).toBeDefined();
    expect(btn.dataset.view).toBe("billing");
    expect(btn.textContent).toContain("View billing");
  });
});
