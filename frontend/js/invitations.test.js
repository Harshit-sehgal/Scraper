/* ═══════════════════════════════════════════
   DataForge — Invitations Smoke Tests
   ═══════════════════════════════════════════ */

import { describe, it, expect, beforeEach, afterEach } from "vitest";

import { createInvitation, respondToInvitation, refreshInvitations } from "./invitations.js";

beforeEach(() => {
  document.body.innerHTML = `
    <div id="invitations-pending-list"></div>
    <div id="invitations-org-list"></div>
    <div id="invite-org-select"></div>
    <div id="invite-email-input"></div>
    <div id="invite-role-select"></div>
    <div id="invite-create-result" class="hidden"></div>
    <div id="invitations-status-filter"></div>
    <div id="invitations-org-filter"></div>
  `;
});

afterEach(() => {
  document.body.innerHTML = "";
});

describe("invitations module", () => {
  it("exports createInvitation as a function", () => {
    expect(typeof createInvitation).toBe("function");
  });

  it("exports respondToInvitation as a function", () => {
    expect(typeof respondToInvitation).toBe("function");
  });

  it("exports refreshInvitations as a function", () => {
    expect(typeof refreshInvitations).toBe("function");
  });
});
