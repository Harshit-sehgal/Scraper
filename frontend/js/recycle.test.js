/* ═══════════════════════════════════════════
   DataForge — Recycle Bin Smoke Tests
   ═══════════════════════════════════════════ */

import { describe, it, expect, beforeEach, afterEach } from "vitest";

import { restoreJob, hardDeleteJob, clearRecycleBin } from "./recycle.js";

beforeEach(() => {
  document.body.innerHTML = `
    <div id="recycle-list"></div>
    <div id="kpi-recycle">0</div>
  `;
});

afterEach(() => {
  document.body.innerHTML = "";
});

describe("recycle module", () => {
  it("exports restoreJob as a function", () => {
    expect(typeof restoreJob).toBe("function");
  });

  it("exports hardDeleteJob as a function", () => {
    expect(typeof hardDeleteJob).toBe("function");
  });

  it("exports clearRecycleBin as a function", () => {
    expect(typeof clearRecycleBin).toBe("function");
  });
});
