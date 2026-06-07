/* ═══════════════════════════════════════════
   DataForge — URL Analyzer Tests
   ═══════════════════════════════════════════ */

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import {
  toggleAllFields,
  clearAnalysis,
  getSelectorsMap,
  getAnalyzedFields,
  renderAnalysisInfo,
  renderFieldList,
  renderAcquisitionBanner,
} from "./analyzer.js";

// ─── Setup / Teardown ──────────────────────────────────────────────────────

beforeEach(() => {
  document.body.innerHTML = `
    <div id="analyze-field-list"></div>
    <div id="analyze-field-count"></div>
    <div id="analyze-results" class="hidden"></div>
    <div id="analyze-error" class="hidden"></div>
    <div id="analyze-error-text"></div>
    <input id="inp-analyze-url" value="" />
    <div id="ai-structure"></div>
    <div id="ai-records"></div>
    <div id="ai-antibot"></div>
    <div id="ai-fetch-time"></div>
    <div id="acquisition-banner" class="hidden"></div>
  `;
});

afterEach(() => {
  document.body.innerHTML = "";
});

// ─── State Accessors ────────────────────────────────────────────────────────

describe("getSelectorsMap() / getAnalyzedFields()", () => {
  it("returns null / empty array before any analysis", () => {
    expect(getSelectorsMap()).toBeNull();
    expect(getAnalyzedFields()).toEqual([]);
  });
});

// ─── clearAnalysis ──────────────────────────────────────────────────────────

describe("clearAnalysis()", () => {
  it("resets state and hides panels", () => {
    // Set some state first
    const results = document.getElementById("analyze-results");
    const error = document.getElementById("analyze-error");
    results.classList.remove("hidden");
    error.classList.remove("hidden");
    document.getElementById("inp-analyze-url").value = "http://example.com";

    clearAnalysis();

    expect(getSelectorsMap()).toBeNull();
    expect(getAnalyzedFields()).toEqual([]);
    expect(results.classList.contains("hidden")).toBe(true);
    expect(error.classList.contains("hidden")).toBe(true);
    expect(document.getElementById("inp-analyze-url").value).toBe("");
  });
});

// ─── toggleAllFields ───────────────────────────────────────────────────────

describe("toggleAllFields()", () => {
  beforeEach(() => {
    const list = document.getElementById("analyze-field-list");
    list.innerHTML = `
      <div class="analyze-field-item selected" data-index="0">
        <input type="checkbox" class="analyze-field-checkbox" checked data-index="0">
        <span class="analyze-field-name">Field A</span>
      </div>
      <div class="analyze-field-item selected" data-index="1">
        <input type="checkbox" class="analyze-field-checkbox" checked data-index="1">
        <span class="analyze-field-name">Field B</span>
      </div>
      <div class="analyze-field-item" data-index="2">
        <input type="checkbox" class="analyze-field-checkbox" data-index="2">
        <span class="analyze-field-name">Field C</span>
      </div>
    `;
  });

  it("unchecks all when select=false", () => {
    toggleAllFields(false);
    const checkboxes = document.querySelectorAll(".analyze-field-checkbox");
    const items = document.querySelectorAll(".analyze-field-item");
    checkboxes.forEach((cb) => expect(cb.checked).toBe(false));
    items.forEach((item) => expect(item.classList.contains("selected")).toBe(false));
  });

  it("checks all when select=true", () => {
    // Set all unchecked first
    toggleAllFields(false);
    toggleAllFields(true);
    const checkboxes = document.querySelectorAll(".analyze-field-checkbox");
    const items = document.querySelectorAll(".analyze-field-item");
    checkboxes.forEach((cb) => expect(cb.checked).toBe(true));
    items.forEach((item) => expect(item.classList.contains("selected")).toBe(true));
  });

  it("works with empty field list", () => {
    document.getElementById("analyze-field-list").innerHTML = "";
    // Should not throw
    toggleAllFields(true);
    toggleAllFields(false);
  });
});

// ─── renderAnalysisInfo ─────────────────────────────────────────────────────

describe("renderAnalysisInfo()", () => {
  it("renders page structure with confidence", () => {
    renderAnalysisInfo({
      page_structure: "table",
      structure_confidence: 0.85,
      estimated_record_count: 42,
      anti_bot_score: 0.2,
      fetch_time_ms: 3200,
    });
    expect(document.getElementById("ai-structure").textContent).toContain("table");
    expect(document.getElementById("ai-structure").textContent).toContain("85%");
    expect(document.getElementById("ai-records").textContent).toContain("42");
    expect(document.getElementById("ai-fetch-time").textContent).toContain("3.2s");
  });

  it("renders high anti-bot risk in red", () => {
    renderAnalysisInfo({ anti_bot_score: 0.85 });
    const el = document.getElementById("ai-antibot");
    expect(el.innerHTML).toContain("High");
    expect(el.innerHTML).toContain("85%");
  });

  it("renders medium anti-bot risk in yellow/amber", () => {
    renderAnalysisInfo({ anti_bot_score: 0.45 });
    const el = document.getElementById("ai-antibot");
    expect(el.innerHTML).toContain("Medium");
    expect(el.innerHTML).toContain("45%");
  });

  it("renders low anti-bot risk in green", () => {
    renderAnalysisInfo({ anti_bot_score: 0.15 });
    const el = document.getElementById("ai-antibot");
    expect(el.innerHTML).toContain("Low");
    expect(el.innerHTML).toContain("15%");
  });

  it("handles missing fields gracefully", () => {
    renderAnalysisInfo({});
    expect(document.getElementById("ai-structure").textContent).toContain("unknown");
    expect(document.getElementById("ai-records").textContent).toContain("?");
    expect(document.getElementById("ai-antibot").innerHTML).toContain("0%");
  });
});

// ─── renderFieldList ───────────────────────────────────────────────────────

describe("renderFieldList()", () => {
  it("renders fields with name, type, example, confidence", () => {
    renderFieldList([
      { name: "company_name", type: "string", example_value: "Acme Inc", confidence: 0.92 },
      { name: "rating", type: "float", example_value: "4.5", confidence: 0.75 },
    ]);
    const el = document.getElementById("analyze-field-list");
    expect(el.innerHTML).toContain("company_name");
    expect(el.innerHTML).toContain("rating");
    expect(el.innerHTML).toContain("Acme Inc");
    expect(el.innerHTML).toContain("92%");
    expect(el.innerHTML).toContain("75%");
  });

  it("shows empty state when no fields", () => {
    renderFieldList([]);
    expect(document.getElementById("analyze-field-list").innerHTML).toContain("No data fields detected");
  });

  it("truncates long example values to 60 chars", () => {
    renderFieldList([{ name: "desc", example_value: "a".repeat(100), confidence: 0.5 }]);
    const el = document.getElementById("analyze-field-list");
    expect(el.innerHTML).toContain("a".repeat(60));
    expect(el.innerHTML).not.toContain("a".repeat(61));
  });

  it("updates field count", () => {
    renderFieldList([{ name: "a" }, { name: "b" }, { name: "c" }]);
    expect(document.getElementById("analyze-field-count").textContent).toBe("3");
  });
});

// ─── renderAcquisitionBanner ───────────────────────────────────────────────

describe("renderAcquisitionBanner()", () => {
  it("renders direct state", () => {
    renderAcquisitionBanner({ acquisition_lineage: { state: "direct" } }, "http://example.com");
    const banner = document.getElementById("acquisition-banner");
    expect(banner.classList.contains("direct")).toBe(true);
    expect(banner.innerHTML).toContain("Page loaded successfully");
  });

  it("renders recovered state with user message", () => {
    renderAcquisitionBanner(
      { acquisition_lineage: { state: "recovered", user_message: "Recovered via search form" } },
      "http://example.com",
    );
    const banner = document.getElementById("acquisition-banner");
    expect(banner.classList.contains("recovered")).toBe(true);
    expect(banner.innerHTML).toContain("Recovered fresh results via search form submission");
  });

  it("renders session-expired state", () => {
    renderAcquisitionBanner({ acquisition_lineage: { state: "session_expired" } }, "http://example.com");
    const banner = document.getElementById("acquisition-banner");
    expect(banner.classList.contains("expired")).toBe(true);
  });

  it("renders empty response banner", () => {
    renderAcquisitionBanner(
      { acquisition_lineage: { state: "empty_response" }, empty_check: { is_empty: true, message: "No data found" } },
      "http://example.com",
    );
    const banner = document.getElementById("acquisition-banner");
    expect(banner.classList.contains("empty")).toBe(true);
    expect(banner.innerHTML).toContain("No data found");
  });

  it("renders session-bound banner", () => {
    renderAcquisitionBanner({ acquisition_lineage: { state: "direct", session_bound: true } }, "http://example.com");
    const banner = document.getElementById("acquisition-banner");
    expect(banner.classList.contains("session")).toBe(true);
    expect(banner.innerHTML).toContain("ephemeral session parameters");
  });

  it("renders canonical URL when different from input", () => {
    renderAcquisitionBanner(
      { acquisition_lineage: { state: "direct" }, canonical_url: "http://canonical.example" },
      "http://original.example",
    );
    const banner = document.getElementById("acquisition-banner");
    expect(banner.innerHTML).toContain("Canonical");
    expect(banner.innerHTML).toContain("canonical.example");
  });

  it("renders empty check suggestions", () => {
    renderAcquisitionBanner(
      {
        acquisition_lineage: { state: "empty_response" },
        empty_check: { is_empty: true, suggestions: ["Try without query params"] },
      },
      "http://example.com",
    );
    const banner = document.getElementById("acquisition-banner");
    expect(banner.innerHTML).toContain("Suggestion");
    expect(banner.innerHTML).toContain("Try without query params");
  });

  it("handles missing data gracefully", () => {
    renderAcquisitionBanner({}, "http://example.com");
    const banner = document.getElementById("acquisition-banner");
    expect(banner.classList.contains("direct")).toBe(true);
    expect(banner.innerHTML).toContain("Page loaded successfully");
  });
});
