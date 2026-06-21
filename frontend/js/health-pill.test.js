/* ═══════════════════════════════════════════
   DataForge — Health Pill Smoke Tests
   ═══════════════════════════════════════════ */

import { describe, it, expect, beforeEach, afterEach } from "vitest";

import { startHealthPill } from "./health-pill.js";

beforeEach(() => {
  document.body.innerHTML = `
    <div id="health-pill" data-state="unknown">checking…</div>
  `;
});

afterEach(() => {
  document.body.innerHTML = "";
});

describe("health-pill module", () => {
  it("exports startHealthPill as a function", () => {
    expect(typeof startHealthPill).toBe("function");
  });
});
