/* ═══════════════════════════════════════════
   DataForge — API Keys Page Smoke Tests
   ═══════════════════════════════════════════ */

import { describe, it, expect, beforeEach, afterEach } from "vitest";

import {
  refreshApiKeysPage,
  saveApiKeyFromPage,
  clearApiKeyFromPage,
  toggleApiKeyVisibility,
  saveAdminKeyFromPage,
  clearAdminKeyFromPage,
  toggleAdminKeyVisibility,
  logoutFromPage,
} from "./api-keys-page.js";

beforeEach(() => {
  document.body.innerHTML = `
    <div id="api-key-input"></div>
    <div id="api-key-status">Not set</div>
    <div id="admin-key-input"></div>
    <div id="admin-key-status">Not set</div>
    <div id="session-status">Checking...</div>
    <div id="session-info"></div>
  `;
});

afterEach(() => {
  document.body.innerHTML = "";
});

describe("api-keys-page module", () => {
  it("exports refreshApiKeysPage as a function", () => {
    expect(typeof refreshApiKeysPage).toBe("function");
  });

  it("exports saveApiKeyFromPage as a function", () => {
    expect(typeof saveApiKeyFromPage).toBe("function");
  });

  it("exports clearApiKeyFromPage as a function", () => {
    expect(typeof clearApiKeyFromPage).toBe("function");
  });

  it("exports toggleApiKeyVisibility as a function", () => {
    expect(typeof toggleApiKeyVisibility).toBe("function");
  });

  it("exports saveAdminKeyFromPage as a function", () => {
    expect(typeof saveAdminKeyFromPage).toBe("function");
  });

  it("exports clearAdminKeyFromPage as a function", () => {
    expect(typeof clearAdminKeyFromPage).toBe("function");
  });

  it("exports toggleAdminKeyVisibility as a function", () => {
    expect(typeof toggleAdminKeyVisibility).toBe("function");
  });

  it("exports logoutFromPage as a function", () => {
    expect(typeof logoutFromPage).toBe("function");
  });
});
