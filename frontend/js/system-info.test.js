/* ═══════════════════════════════════════════
   DataForge — System Info Smoke Tests
   ═══════════════════════════════════════════ */

import { describe, it, expect } from "vitest";

import { startSystemInfo, stopSystemInfo } from "./system-info.js";

describe("system-info module", () => {
  it("exports startSystemInfo as a function", () => {
    expect(typeof startSystemInfo).toBe("function");
  });

  it("exports stopSystemInfo as a function", () => {
    expect(typeof stopSystemInfo).toBe("function");
  });
});
