/* ═══════════════════════════════════════════
   DataForge — Domain Health Smoke Tests
   ═══════════════════════════════════════════ */

import { describe, it, expect, beforeEach, afterEach } from "vitest";

import { renderDomainHealth } from "./domain-health.js";

beforeEach(() => {
  document.body.innerHTML = `<div id="dash-domains"></div>`;
});

afterEach(() => {
  document.body.innerHTML = "";
});

describe("domain-health module", () => {
  it("exports renderDomainHealth as a function", () => {
    expect(typeof renderDomainHealth).toBe("function");
  });

  it("renders empty state when no domains are monitored", () => {
    renderDomainHealth({ domains: { total_monitored: 0 } });
    const el = document.getElementById("dash-domains");
    expect(el?.innerHTML).toContain("No domains monitored");
  });

  it("renders metrics grid with domain data", () => {
    renderDomainHealth({
      domains: {
        total_monitored: 100,
        healthy: 80,
        degrading: 10,
        unhealthy: 5,
        critical: 5,
      },
    });
    const el = document.getElementById("dash-domains");
    expect(el?.innerHTML).toContain("100");
    expect(el?.innerHTML).toContain("80");
    expect(el?.innerHTML).toContain("80%");
  });
});
