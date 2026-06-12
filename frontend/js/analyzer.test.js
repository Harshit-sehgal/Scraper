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
  renderIntelligencePanel,
  renderWorkflowDraftPanel,
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
    <div id="url-intelligence-panel" class="hidden">
      <span id="intelligence-confidence"></span>
      <span id="intelligence-classification"></span>
      <span id="intelligence-risk"></span>
      <span id="intelligence-recommended-mode"></span>
      <span id="intelligence-reason"></span>
      <div id="intelligence-steps-container" class="hidden">
        <ul id="intelligence-steps"></ul>
      </div>
      <div id="intelligence-actions" class="hidden"></div>
    </div>
    <div id="workflow-builder-panel" class="hidden">
      <span id="workflow-builder-status"></span>
      <input id="workflow-builder-start-url" />
      <code id="workflow-builder-original-url"></code>
      <p id="workflow-builder-reason"></p>
      <div id="workflow-builder-fields"></div>
      <textarea id="workflow-builder-mapping"></textarea>
      <div id="workflow-builder-preview-table"></div>
      <ol id="workflow-builder-timeline"></ol>
      <div id="workflow-builder-failure" class="hidden"></div>
    </div>
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

// ─── renderIntelligencePanel ───────────────────────────────────────────────

describe("renderIntelligencePanel()", () => {
  it("renders normal URL direct scrape recommendation", () => {
    renderIntelligencePanel({
      classifications: [{ type: "normal_static_page", confidence: 0.95, evidence: "No special signals detected." }],
      risk_level: "low",
      recommended_mode: "direct_scrape",
      user_message: "This looks like a normal page. Recommended mode: Direct Scrape.",
      next_steps: ["Preview extraction before full run."],
    });

    expect(document.getElementById("intelligence-classification").textContent).toContain("normal static page");
    expect(document.getElementById("intelligence-recommended-mode").textContent).toContain("direct scrape");
    expect(document.getElementById("intelligence-actions").innerHTML).toContain("Continue with Direct Scrape");
  });

  it("renders session URL workflow choices without raw token values", () => {
    renderIntelligencePanel({
      url: "https://example.com/search/results?sessionId=abc1...x789",
      classifications: [{ type: "session_bound_url", confidence: 0.95, evidence: "sessionId detected" }],
      risk_level: "high",
      recommended_mode: "workflow_replay_recommended",
      user_message: "This URL looks temporary because it contains sessionId. Direct scraping may fail later.",
      technical_findings: ["Temporary parameter detected: sessionId=abc1...x789"],
      suggested_start_urls: [{ url: "https://example.com/search", confidence: 0.72 }],
    });

    const panel = document.getElementById("url-intelligence-panel");
    expect(panel.textContent).toContain("sessionId");
    expect(panel.innerHTML).toContain("Try Direct Scrape Once");
    expect(panel.innerHTML).toContain("Create Reliable Workflow");
    expect(panel.innerHTML).not.toContain("abc123xyz789");
  });

  it("renders blocked URL state with disabled action", () => {
    renderIntelligencePanel({
      classifications: [{ type: "unsafe_url", confidence: 1, evidence: "Safety validation rejected this target." }],
      risk_level: "blocked",
      recommended_mode: "blocked_or_unsafe",
      user_message: "This URL is blocked by the safety policy.",
      next_steps: ["Choose a public http(s) URL."],
    });

    expect(document.getElementById("intelligence-risk").textContent).toBe("Blocked");
    expect(document.getElementById("intelligence-actions").innerHTML).toContain("disabled");
    expect(document.getElementById("intelligence-actions").innerHTML).toContain("Blocked by safety policy");
  });
});

// ─── renderWorkflowDraftPanel ──────────────────────────────────────────────

describe("renderWorkflowDraftPanel()", () => {
  it("renders a workflow replay draft handoff with redacted original URL", () => {
    renderWorkflowDraftPanel({
      status: "draft",
      original_url: "https://example.com/search/results?sessionId=abc1...x789",
      selected_start_url: "https://example.com/search",
      detected_reason: "This URL looks temporary because it contains sessionId.",
      recommended_start_urls: [{ url: "https://example.com/search", confidence: 0.72 }],
      detected_fields: [
        {
          label: "Keyword",
          selector: "#q",
          confidence: 0.9,
        },
      ],
    });

    const panel = document.getElementById("workflow-builder-panel");
    expect(panel.classList.contains("hidden")).toBe(false);
    expect(document.getElementById("workflow-builder-status").textContent).toBe("draft");
    expect(document.getElementById("workflow-builder-start-url").value).toBe("https://example.com/search");
    expect(document.getElementById("workflow-builder-original-url").textContent).toContain("abc1...x789");
    expect(document.getElementById("workflow-builder-original-url").textContent).not.toContain("abc123xyz789");
    expect(document.getElementById("workflow-builder-fields").textContent).toContain("Keyword");
    expect(document.getElementById("workflow-builder-mapping").value).toContain("suggested_start_urls");
    expect(document.getElementById("workflow-builder-timeline").textContent).toContain("Draft created");
  });
});
