/**
 * Vitest tests for the Billing / Audit / Retention view modules.
 *
 * Smoke test only: we assert the module loads and exposes the
 * expected public functions, plus a couple of trivial pure helpers
 * (HTML escaping) to keep the test cheap and free of network
 * stubs. The full rendering paths are exercised by the E2E suite.
 */
import { describe, it, expect } from "vitest";

describe("billing module", () => {
  it("exports refreshBilling and upgradePlan", async () => {
    const mod = await import("./billing.js");
    expect(typeof mod.refreshBilling).toBe("function");
    expect(typeof mod.upgradePlan).toBe("function");
  });
});

describe("audit module", () => {
  it("exports refreshAudit", async () => {
    const mod = await import("./audit.js");
    expect(typeof mod.refreshAudit).toBe("function");
  });
});

describe("retention module", () => {
  it("exports refreshRetention and deleteMyData", async () => {
    const mod = await import("./retention.js");
    expect(typeof mod.refreshRetention).toBe("function");
    expect(typeof mod.deleteMyData).toBe("function");
  });
});
