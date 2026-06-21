/**
 * Vitest tests for the topbar health pill.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";

describe("health-pill module", () => {
  beforeEach(() => {
    document.body.innerHTML = '<span id="health-pill"></span>';
  });

  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("exports startHealthPill and stopHealthPill", async () => {
    const mod = await import("./health-pill.js");
    expect(typeof mod.startHealthPill).toBe("function");
    expect(typeof mod.stopHealthPill).toBe("function");
  });

  it("getHealthState returns a status object", async () => {
    const mod = await import("./health-pill.js");
    const state = mod.getHealthState();
    expect(state).toHaveProperty("status");
    expect(state).toHaveProperty("error");
  });

  it("is idempotent when started twice", async () => {
    const mod = await import("./health-pill.js");
    mod.startHealthPill();
    mod.startHealthPill();
    mod.stopHealthPill();
  });
});
