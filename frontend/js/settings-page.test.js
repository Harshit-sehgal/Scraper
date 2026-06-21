/* ═══════════════════════════════════════════
   DataForge — Settings Page Smoke Tests
   ═══════════════════════════════════════════ */

import { describe, it, expect, beforeEach, afterEach } from "vitest";

import { refreshSettingsPage, setThemeMode } from "./settings-page.js";

beforeEach(() => {
  document.body.innerHTML = `
    <div id="view-settings"></div>
    <div id="settings-api-url"></div>
    <div id="settings-theme-toggle"></div>
  `;
});

afterEach(() => {
  document.body.innerHTML = "";
});

describe("settings-page module", () => {
  it("exports refreshSettingsPage as a function", () => {
    expect(typeof refreshSettingsPage).toBe("function");
  });

  it("exports setThemeMode as a function", () => {
    expect(typeof setThemeMode).toBe("function");
  });
});
