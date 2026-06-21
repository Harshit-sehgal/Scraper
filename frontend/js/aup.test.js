/* ═══════════════════════════════════════════
   DataForge — AUP Smoke Tests
   ═══════════════════════════════════════════ */

import { describe, it, expect, beforeEach, afterEach } from "vitest";

import { checkAndRenderAupBanner, acceptAup, dismissAupBanner } from "./aup.js";

beforeEach(() => {
  document.body.innerHTML = `
    <div id="aup-banner" style="display: none"></div>
  `;
});

afterEach(() => {
  document.body.innerHTML = "";
});

describe("aup module", () => {
  it("exports checkAndRenderAupBanner as a function", () => {
    expect(typeof checkAndRenderAupBanner).toBe("function");
  });

  it("exports acceptAup as a function", () => {
    expect(typeof acceptAup).toBe("function");
  });

  it("exports dismissAupBanner as a function", () => {
    expect(typeof dismissAupBanner).toBe("function");
  });
});
