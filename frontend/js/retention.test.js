/* ═══════════════════════════════════════════
   DataForge — Retention Smoke Tests
   ═══════════════════════════════════════════ */

import { describe, it, expect, beforeEach, afterEach } from "vitest";

import { refreshRetention, deleteMyData } from "./retention.js";

beforeEach(() => {
  document.body.innerHTML = `
    <div id="retention-recycle-summary"></div>
    <div id="btn-delete-my-data"></div>
  `;
});

afterEach(() => {
  document.body.innerHTML = "";
});

describe("retention module", () => {
  it("exports refreshRetention as a function", () => {
    expect(typeof refreshRetention).toBe("function");
  });

  it("exports deleteMyData as a function", () => {
    expect(typeof deleteMyData).toBe("function");
  });
});
