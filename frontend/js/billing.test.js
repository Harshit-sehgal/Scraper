/**
 * Vitest tests for the Billing / Audit / Retention view modules.
 *
 * Smoke test only: we assert the module loads and exposes the
 * expected public functions. Full rendering paths are exercised
 * by the E2E suite (frontend/e2e/).
 *
 * We mock ./api.js to break the import chain that triggers
 * module-level window references in views.js via jobs.js.
 */
import { describe, it, expect, vi } from "vitest";

vi.mock("./api.js", () => ({
  apiFetch: vi.fn(),
  endpoints: {},
  isMockMode: vi.fn(() => false),
  getApiKey: vi.fn(() => ""),
  setApiKey: vi.fn(),
  isKeyModalVisible: vi.fn(() => false),
  closeKeyModal: vi.fn(),
  saveKeyFromModal: vi.fn(),
  clearApiKey: vi.fn(),
  showApiKeyPrompt: vi.fn(),
  showAdminKeyPrompt: vi.fn(),
  onAuthChange: vi.fn(() => vi.fn()),
  checkSession: vi.fn(),
  isSessionAuthenticated: vi.fn(() => false),
  getSessionUser: vi.fn(() => null),
  loginWithApiKey: vi.fn(),
  logoutSession: vi.fn(),
  getAdminKey: vi.fn(() => ""),
  setAdminKey: vi.fn(),
  markSignedOut: vi.fn(),
  isAdminOrOperator: vi.fn(() => false),
  getSessionRole: vi.fn(() => ""),
  API: "",
  default: {},
}));

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
