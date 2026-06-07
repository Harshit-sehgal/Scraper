/* ═══════════════════════════════════════════
   DataForge — Domain Health Rendering Tests
   ═══════════════════════════════════════════ */

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { renderDomainHealth } from "./domain-health.js";

/**
 * Set up the DOM elements that renderDomainHealth targets.
 */
function setupDOM() {
  const container = document.createElement("div");
  container.id = "dash-domains";
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

const HEALTH_DATA = {
  domains: {
    total_monitored: 50,
    healthy: 30,
    degrading: 10,
    unhealthy: 7,
    critical: 3,
  },
};

// ─── Basic Rendering ───

describe("renderDomainHealth", () => {
  it("renders total monitored count", () => {
    renderDomainHealth(HEALTH_DATA);
    const el = document.getElementById("dash-domains");
    expect(el.innerHTML).toContain(">50<");
  });

  it("renders healthy count", () => {
    renderDomainHealth(HEALTH_DATA);
    const el = document.getElementById("dash-domains");
    expect(el.innerHTML).toContain(">30<");
  });

  it("renders degrading count", () => {
    renderDomainHealth(HEALTH_DATA);
    const el = document.getElementById("dash-domains");
    expect(el.innerHTML).toContain(">10<");
  });

  it("renders unhealthy count", () => {
    renderDomainHealth(HEALTH_DATA);
    const el = document.getElementById("dash-domains");
    expect(el.innerHTML).toContain(">7<");
  });

  it("renders critical count", () => {
    renderDomainHealth(HEALTH_DATA);
    const el = document.getElementById("dash-domains");
    expect(el.innerHTML).toContain(">3<");
  });

  it("renders health rate percentage", () => {
    renderDomainHealth(HEALTH_DATA);
    const el = document.getElementById("dash-domains");
    // 30/50 = 60%
    expect(el.innerHTML).toContain("60%");
  });

  it("renders 6 metric cards", () => {
    renderDomainHealth(HEALTH_DATA);
    const el = document.getElementById("dash-domains");
    const cards = el.querySelectorAll(".dash-metric");
    expect(cards.length).toBe(6);
  });

  it("renders health bar with correct widths", () => {
    renderDomainHealth(HEALTH_DATA);
    const el = document.getElementById("dash-domains");
    // healthy: 30/50 = 60%, degrading: 10/50 = 20%, bad: 10/50 = 20%
    const fills = el.querySelectorAll(".dash-health-fill");
    expect(fills.length).toBe(3);
    expect(fills[0].style.width).toBe("60%");
    expect(fills[1].style.width).toBe("20%");
    expect(fills[2].style.width).toBe("20%");
  });

  // ─── Empty State ───

  it("shows empty state when no domains monitored", () => {
    renderDomainHealth({ domains: { total_monitored: 0 } });
    const el = document.getElementById("dash-domains");
    expect(el.innerHTML).toContain("No domains monitored yet");
    expect(el.querySelectorAll(".dash-metric").length).toBe(0);
  });

  it("shows empty state when domains is empty", () => {
    renderDomainHealth({});
    const el = document.getElementById("dash-domains");
    expect(el.innerHTML).toContain("No domains monitored yet");
  });

  // ─── Edge Cases ───

  it("does not crash when container is missing", () => {
    document.body.innerHTML = "";
    expect(() => renderDomainHealth(HEALTH_DATA)).not.toThrow();
  });

  it("does not crash on null data", () => {
    expect(() => renderDomainHealth(null)).not.toThrow();
  });

  it("does not crash on undefined data", () => {
    expect(() => renderDomainHealth(undefined)).not.toThrow();
  });

  it("handles zero health rate gracefully", () => {
    renderDomainHealth({ domains: { total_monitored: 10, healthy: 0, degrading: 0, unhealthy: 0, critical: 0 } });
    const el = document.getElementById("dash-domains");
    expect(el.innerHTML).toContain("0%");
    const fills = el.querySelectorAll(".dash-health-fill");
    expect(fills[0].style.width).toBe("0%");
  });

  it("handles partial sub-object with missing fields", () => {
    renderDomainHealth({ domains: { total_monitored: 5 } });
    const el = document.getElementById("dash-domains");
    // Missing healthy/degrading/unhealthy/critical should default to 0
    expect(el.innerHTML).toContain("5");
    expect(el.innerHTML).toContain("0%");
  });

  it("renders all domains critical edge case", () => {
    renderDomainHealth({ domains: { total_monitored: 10, healthy: 0, degrading: 0, unhealthy: 0, critical: 10 } });
    const el = document.getElementById("dash-domains");
    expect(el.innerHTML).toContain(">10<");
    expect(el.innerHTML).toContain("0%");
    const fills = el.querySelectorAll(".dash-health-fill");
    // 0% healthy + 0% degrading + 100% bad (unhealthy + critical = 10/10)
    expect(fills[2].style.width).toBe("100%");
  });

  it("renders 100% health rate", () => {
    renderDomainHealth({ domains: { total_monitored: 25, healthy: 25, degrading: 0, unhealthy: 0, critical: 0 } });
    const el = document.getElementById("dash-domains");
    expect(el.innerHTML).toContain("100%");
  });
});
