import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { renderTelemetry } from "./telemetry.js";

/**
 * Set up the DOM elements that renderTelemetry targets.
 */
function setupDom() {
  const container = document.createElement("div");
  container.innerHTML = `
    <div id="dash-telemetry"><div class="dash-loading">Loading...</div></div>
  `;
  document.body.appendChild(container);
}

/**
 * Sample telemetry data (all fields populated).
 */
const SAMPLE_DATA = Object.freeze({
  recent_scrapes: 42,
  recent_successes: 38,
  recent_failures: 4,
  success_rate: 0.9048,
});

beforeEach(() => {
  setupDom();
});

afterEach(() => {
  document.body.innerHTML = "";
});

// ═══════════════════════════════════════════════════════════════════════
// renderTelemetry — Basic Rendering
// ═══════════════════════════════════════════════════════════════════════

describe("renderTelemetry", () => {
  it("renders recent_scrapes count", () => {
    renderTelemetry(SAMPLE_DATA);
    const el = document.getElementById("dash-telemetry");
    expect(el.textContent).toContain("42");
  });

  it("renders recent_successes count", () => {
    renderTelemetry(SAMPLE_DATA);
    const el = document.getElementById("dash-telemetry");
    expect(el.textContent).toContain("38");
  });

  it("renders recent_failures count", () => {
    renderTelemetry(SAMPLE_DATA);
    const el = document.getElementById("dash-telemetry");
    expect(el.textContent).toContain("4");
  });

  it("renders success rate as percentage", () => {
    renderTelemetry(SAMPLE_DATA);
    const el = document.getElementById("dash-telemetry");
    expect(el.textContent).toContain("90%");
  });

  it("shows em dash for null success_rate", () => {
    renderTelemetry({ recent_scrapes: 0, recent_successes: 0, recent_failures: 0, success_rate: null });
    const el = document.getElementById("dash-telemetry");
    expect(el.textContent).toContain("—");
  });

  it("uses zero defaults for missing fields", () => {
    renderTelemetry({});
    const el = document.getElementById("dash-telemetry");
    expect(el.textContent).toContain("0");
  });

  it("does not crash when container element is missing", () => {
    const el = document.getElementById("dash-telemetry");
    el.remove();
    expect(() => renderTelemetry(SAMPLE_DATA)).not.toThrow();
  });

  it("handles null/undefined gracefully", () => {
    expect(() => renderTelemetry(null)).not.toThrow();
    expect(() => renderTelemetry(undefined)).not.toThrow();
  });

  it("renders the correct grid structure", () => {
    renderTelemetry(SAMPLE_DATA);
    const el = document.getElementById("dash-telemetry");
    const grid = el.querySelector(".dash-metrics-grid");
    expect(grid).toBeDefined();
    const metrics = grid.querySelectorAll(".dash-metric");
    expect(metrics.length).toBe(4);
  });

  it("color-codes successes and failures", () => {
    renderTelemetry(SAMPLE_DATA);
    const el = document.getElementById("dash-telemetry");
    // Success metric has color:var(--success)
    expect(el.innerHTML).toContain("var(--success)");
    // Failure metric has color:var(--danger)
    expect(el.innerHTML).toContain("var(--danger)");
  });
});
