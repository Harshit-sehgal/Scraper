/* ═══════════════════════════════════════════
   DataForge — Audit Smoke Tests
   ═══════════════════════════════════════════ */

import { describe, it, expect, beforeEach, afterEach } from "vitest";

import { refreshAudit } from "./audit.js";

beforeEach(() => {
  document.body.innerHTML = `
    <div id="audit-list"></div>
    <div id="audit-category-filter"></div>
    <div id="audit-limit-filter"></div>
  `;
});

afterEach(() => {
  document.body.innerHTML = "";
});

describe("audit module", () => {
  it("exports refreshAudit as a function", () => {
    expect(typeof refreshAudit).toBe("function");
  });
});
