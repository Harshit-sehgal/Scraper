/**
 * Vitest tests for the SaaS frontend modules:
 *   - Email Verification
 *   - Password Reset
 *   - Team Invitations
 *
 * Smoke test only: we assert the module loads and exposes the
 * expected public functions. Full rendering and network paths are
 * exercised by the E2E suite (frontend/e2e/).
 *
 * We mock ./api.js to break the import chain that would otherwise
 * trigger module-level window references in views.js via jobs.js.
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

describe("email-verification module", () => {
  it("exports refreshEmailVerification, sendEmailVerification, and verifyEmailToken", async () => {
    const mod = await import("./email-verification.js");
    expect(typeof mod.refreshEmailVerification).toBe("function");
    expect(typeof mod.sendEmailVerification).toBe("function");
    expect(typeof mod.verifyEmailToken).toBe("function");
  });
});

describe("password-reset module", () => {
  it("exports requestPasswordReset and confirmPasswordReset", async () => {
    const mod = await import("./password-reset.js");
    expect(typeof mod.requestPasswordReset).toBe("function");
    expect(typeof mod.confirmPasswordReset).toBe("function");
  });
});

describe("invitations module", () => {
  it("exports refreshInvitations, respondToInvitation, createInvitation, and onInvitationsFilterChanged", async () => {
    const mod = await import("./invitations.js");
    expect(typeof mod.refreshInvitations).toBe("function");
    expect(typeof mod.respondToInvitation).toBe("function");
    expect(typeof mod.createInvitation).toBe("function");
    expect(typeof mod.onInvitationsFilterChanged).toBe("function");
  });
});
