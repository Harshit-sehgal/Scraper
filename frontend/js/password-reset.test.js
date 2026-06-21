/* ═══════════════════════════════════════════
   DataForge — Password Reset Smoke Tests
   ═══════════════════════════════════════════ */

import { describe, it, expect, beforeEach, afterEach } from "vitest";

import { requestPasswordReset, confirmPasswordReset } from "./password-reset.js";

beforeEach(() => {
  document.body.innerHTML = `
    <div id="pwd-reset-email-input"></div>
    <div id="pwd-reset-request-result" class="hidden"></div>
    <div id="pwd-reset-token-input"></div>
    <div id="pwd-reset-new-password"></div>
    <div id="pwd-reset-confirm-result" class="hidden"></div>
  `;
});

afterEach(() => {
  document.body.innerHTML = "";
});

describe("password-reset module", () => {
  it("exports requestPasswordReset as a function", () => {
    expect(typeof requestPasswordReset).toBe("function");
  });

  it("exports confirmPasswordReset as a function", () => {
    expect(typeof confirmPasswordReset).toBe("function");
  });
});
