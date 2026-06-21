/* ═══════════════════════════════════════════
   DataForge — Email Verification Smoke Tests
   ═══════════════════════════════════════════ */

import { describe, it, expect, beforeEach, afterEach } from "vitest";

import { sendEmailVerification, verifyEmailToken, refreshEmailVerification } from "./email-verification.js";

beforeEach(() => {
  document.body.innerHTML = `
    <div id="email-verify-status"></div>
    <div id="email-verify-actions"></div>
    <div id="email-verify-token-input"></div>
    <div id="email-verify-result" class="hidden"></div>
  `;
});

afterEach(() => {
  document.body.innerHTML = "";
});

describe("email-verification module", () => {
  it("exports sendEmailVerification as a function", () => {
    expect(typeof sendEmailVerification).toBe("function");
  });

  it("exports verifyEmailToken as a function", () => {
    expect(typeof verifyEmailToken).toBe("function");
  });

  it("exports refreshEmailVerification as a function", () => {
    expect(typeof refreshEmailVerification).toBe("function");
  });
});
