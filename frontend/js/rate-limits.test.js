import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { renderRateLimits } from "./rate-limits.js";

/**
 * Set up the DOM elements that renderRateLimits targets.
 */
function setupDom() {
  const container = document.createElement("div");
  container.innerHTML = `
    <span id="dash-rate-limit-tier">—</span>
    <div id="dash-rate-limits"><div class="dash-loading">Loading...</div></div>
  `;
  document.body.appendChild(container);
}

/**
 * Sample rate limit stats response (enabled state).
 */
const ENABLED_DATA = Object.freeze({
  enabled: true,
  global_limit_per_window: 600,
  global_window_seconds: 60,
  per_ip_enabled: true,
  per_ip_limit_per_window: 100,
  per_ip_window_seconds: 60,
  active_keys: 5,
  route_limits: {
    "/api/jobs": { max: 30, window_seconds: 60 },
    "/api/url/analyze": { max: 10, window_seconds: 60 },
  },
});

/**
 * Sample rate limit stats response (disabled state).
 */
const DISABLED_DATA = Object.freeze({
  enabled: false,
  global_limit_per_window: 0,
  global_window_seconds: 60,
  per_ip_enabled: false,
  per_ip_limit_per_window: 0,
  per_ip_window_seconds: 60,
  active_keys: 0,
  route_limits: {},
});

/**
 * Sample rate limit stats response (per-IP disabled but global enabled).
 */
const PER_IP_DISABLED_DATA = Object.freeze({
  enabled: true,
  global_limit_per_window: 600,
  global_window_seconds: 60,
  per_ip_enabled: false,
  per_ip_limit_per_window: 0,
  per_ip_window_seconds: 60,
  active_keys: 1,
  route_limits: {},
});

// ─── Helpers ────────────────────────────────────────────────────────────

beforeEach(() => {
  setupDom();
});

afterEach(() => {
  document.body.innerHTML = "";
});

// ═══════════════════════════════════════════════════════════════════════
// renderRateLimits — Basic Rendering
// ═══════════════════════════════════════════════════════════════════════

describe("renderRateLimits", () => {
  it("updates badge text to ENABLED when data.enabled is true", () => {
    renderRateLimits(ENABLED_DATA);
    const badge = document.getElementById("dash-rate-limit-tier");
    expect(badge.textContent).toBe("ENABLED");
  });

  it("updates badge text to DISABLED when data.enabled is false", () => {
    renderRateLimits(DISABLED_DATA);
    const badge = document.getElementById("dash-rate-limit-tier");
    expect(badge.textContent).toBe("DISABLED");
  });

  it("shows empty state when disabled", () => {
    renderRateLimits(DISABLED_DATA);
    const el = document.getElementById("dash-rate-limits");
    expect(el.innerHTML).toContain("Rate limiting is currently disabled");
  });

  it("renders global limit when enabled", () => {
    renderRateLimits(ENABLED_DATA);
    const el = document.getElementById("dash-rate-limits");
    expect(el.innerHTML).toContain("600");
    expect(el.innerHTML).toContain("req / 60s");
  });

  it("renders per-IP limit when enabled", () => {
    renderRateLimits(ENABLED_DATA);
    const el = document.getElementById("dash-rate-limits");
    expect(el.innerHTML).toContain("100");
    expect(el.innerHTML).toContain("req / 60s");
  });

  it("shows DISABLED for per-IP tier when per_ip_enabled is false", () => {
    renderRateLimits(PER_IP_DISABLED_DATA);
    const el = document.getElementById("dash-rate-limits");
    expect(el.innerHTML).toContain("DISABLED");
  });

  it("renders active keys count", () => {
    renderRateLimits(ENABLED_DATA);
    const el = document.getElementById("dash-rate-limits");
    expect(el.innerHTML).toContain("5");
  });

  it("does not crash when badge element is missing", () => {
    const badge = document.getElementById("dash-rate-limit-tier");
    badge.remove();
    expect(() => renderRateLimits(ENABLED_DATA)).not.toThrow();
  });

  it("does not crash when container element is missing", () => {
    const el = document.getElementById("dash-rate-limits");
    el.remove();
    expect(() => renderRateLimits(ENABLED_DATA)).not.toThrow();
  });

  it("handles null/undefined gracefully", () => {
    expect(() => renderRateLimits(null)).not.toThrow();
    expect(() => renderRateLimits(undefined)).not.toThrow();
  });

  it("renders the correct grid structure", () => {
    renderRateLimits(ENABLED_DATA);
    const el = document.getElementById("dash-rate-limits");
    const grid = el.querySelector(".dash-metrics-grid");
    expect(grid).toBeDefined();
    expect(grid.style.gridTemplateColumns).toBe("repeat(2, 1fr)");
    const metrics = grid.querySelectorAll(".dash-metric");
    expect(metrics.length).toBe(3);
  });

  it("sets badge colors to success/soft when enabled", () => {
    renderRateLimits(ENABLED_DATA);
    const badge = document.getElementById("dash-rate-limit-tier");
    expect(badge.style.background).toContain("success-soft");
    expect(badge.style.color).toContain("success");
  });

  it("sets badge colors to danger/soft when disabled", () => {
    renderRateLimits(DISABLED_DATA);
    const badge = document.getElementById("dash-rate-limit-tier");
    expect(badge.style.background).toContain("danger-soft");
    expect(badge.style.color).toContain("danger");
  });
});
