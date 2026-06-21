/* ═══════════════════════════════════════════
   DataForge — Command Palette Smoke Tests
   ═══════════════════════════════════════════ */

import { describe, it, expect, beforeEach, afterEach } from "vitest";

import { openCommandPalette, closeCommandPalette } from "./command-palette.js";

beforeEach(() => {
  document.body.innerHTML = `
    <div id="command-palette-overlay" class="hidden"></div>
    <div id="command-palette-input"></div>
    <div id="command-palette-results"></div>
  `;
});

afterEach(() => {
  document.body.innerHTML = "";
});

describe("command-palette module", () => {
  it("exports openCommandPalette as a function", () => {
    expect(typeof openCommandPalette).toBe("function");
  });

  it("exports closeCommandPalette as a function", () => {
    expect(typeof closeCommandPalette).toBe("function");
  });
});
