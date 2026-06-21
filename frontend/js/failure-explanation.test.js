/* ═══════════════════════════════════════════
   DataForge — Failure Explanation Tests
   ═══════════════════════════════════════════ */

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import {
  classifyJobFailure,
  getFailureExplanation,
  renderFailureBadge,
  renderFailurePanel,
  renderFailureTooltip,
  initFailureBadges,
  attachFailureExplanationToJobRow,
} from "./failure-explanation.js";

// ─── classifyJobFailure ────────────────────────────────────────────────────

describe("classifyJobFailure()", () => {
  it("returns null for a successful job", () => {
    const job = { status: "completed", error: "" };
    expect(classifyJobFailure(job)).toBeNull();
  });

  it("returns null for null job", () => {
    expect(classifyJobFailure(null)).toBeNull();
  });

  it("returns null for undefined job", () => {
    expect(classifyJobFailure(undefined)).toBeNull();
  });

  it("classifies login_required from error message", () => {
    const job = { status: "failed", error: "Login required to access this page" };
    expect(classifyJobFailure(job)).toBe("login_required");
  });

  it("classifies session_expired from error message", () => {
    const job = { status: "failed", error: "Session expired, please login again" };
    expect(classifyJobFailure(job)).toBe("session_expired");
  });

  it("classifies blocked from error message", () => {
    const job = { status: "failed", error: "CAPTCHA challenge detected" };
    expect(classifyJobFailure(job)).toBe("blocked");
  });

  it("classifies blocked from 403 error", () => {
    const job = { status: "error", error: "403 Forbidden" };
    expect(classifyJobFailure(job)).toBe("blocked");
  });

  it("classifies timeout from error message", () => {
    const job = { status: "failed", error: "Request timed out" };
    expect(classifyJobFailure(job)).toBe("timeout");
  });

  it("classifies network_error from error message", () => {
    const job = { status: "failed", error: "Connection refused" };
    expect(classifyJobFailure(job)).toBe("network_error");
  });

  it("classifies network_error from DNS error", () => {
    const job = { status: "failed", error: "dns resolution failed" };
    expect(classifyJobFailure(job)).toBe("network_error");
  });

  it("classifies quota_exceeded from error message", () => {
    const job = { status: "failed", error: "Rate limit exceeded (429)" };
    expect(classifyJobFailure(job)).toBe("quota_exceeded");
  });

  it("classifies selector_not_found from error message", () => {
    const job = { status: "failed", error: "Selector .company-name not found" };
    expect(classifyJobFailure(job)).toBe("selector_not_found");
  });

  it("classifies browser_crash from error message", () => {
    const job = { status: "failed", error: "Browser context closed unexpectedly" };
    expect(classifyJobFailure(job)).toBe("browser_crash");
  });

  it("classifies domain_blocked from error message", () => {
    const job = { status: "failed", error: "Domain not allowed for scraping" };
    expect(classifyJobFailure(job)).toBe("domain_blocked");
  });

  it("classifies session_url from warnings", () => {
    const job = { status: "completed", error: "", warnings: [{ message: "URL contains session parameters" }] };
    expect(classifyJobFailure(job)).toBe("session_url");
  });

  it("classifies partial_extraction from warnings", () => {
    const job = { status: "completed", error: "", warnings: ["Missing fields: partial extraction"] };
    expect(classifyJobFailure(job)).toBe("partial_extraction");
  });

  it("classifies low_quality from warnings", () => {
    const job = { status: "completed", error: "", warnings: [{ message: "Low quality score detected" }] };
    expect(classifyJobFailure(job)).toBe("low_quality");
  });

  it("classifies no_records from empty_result status", () => {
    const job = { status: "empty_result", error: "" };
    expect(classifyJobFailure(job)).toBe("no_records");
  });

  it("classifies partial_extraction from degraded status", () => {
    const job = { status: "degraded", error: "" };
    expect(classifyJobFailure(job)).toBe("partial_extraction");
  });

  it("falls back to unknown for generic failed status", () => {
    const job = { status: "failed", error: "Something went wrong" };
    expect(classifyJobFailure(job)).toBe("unknown");
  });

  it("classifies sign in as login_required", () => {
    const job = { status: "error", error: "Please sign in to continue" };
    expect(classifyJobFailure(job)).toBe("login_required");
  });

  it("classifies ec onn ref as network_error", () => {
    const job = { status: "failed", error: "econnrefused" };
    expect(classifyJobFailure(job)).toBe("network_error");
  });
});

// ─── getFailureExplanation ─────────────────────────────────────────────────

describe("getFailureExplanation()", () => {
  it("returns explanation for known failure type", () => {
    const result = getFailureExplanation("login_required");
    expect(result).toBeDefined();
    expect(result.title).toBe("Login Required");
    expect(result.icon).toBe("🔐");
    expect(result.message).toContain("login");
    expect(result.action).toContain("Auth Profile");
  });

  it("returns unknown explanation for null type", () => {
    const result = getFailureExplanation(null);
    expect(result.title).toBe("Extraction Error");
  });

  it("returns unknown explanation for undefined type", () => {
    const result = getFailureExplanation(undefined);
    expect(result.title).toBe("Extraction Error");
  });

  it("returns unknown explanation for unrecognized type", () => {
    const result = getFailureExplanation("alien_invasion");
    expect(result.title).toBe("Extraction Error");
  });

  it("has all required fields for every failure type", () => {
    const types = [
      "login_required",
      "session_expired",
      "session_url",
      "selector_not_found",
      "blocked",
      "timeout",
      "network_error",
      "no_records",
      "quota_exceeded",
      "domain_blocked",
      "browser_crash",
      "partial_extraction",
      "low_quality",
      "unknown",
    ];
    for (const t of types) {
      const exp = getFailureExplanation(t);
      expect(exp.icon).toBeTruthy();
      expect(exp.title).toBeTruthy();
      expect(exp.message).toBeTruthy();
      expect(exp.detail).toBeTruthy();
      expect(exp.action).toBeTruthy();
    }
  });
});

// ─── renderFailureBadge ────────────────────────────────────────────────────

describe("renderFailureBadge()", () => {
  it("returns empty string for successful job", () => {
    const job = { status: "completed" };
    expect(renderFailureBadge(job)).toBe("");
  });

  it("returns failure badge for failed job", () => {
    const job = { status: "failed", error: "Login required" };
    const html = renderFailureBadge(job);
    expect(html).toContain("failure-badge");
    expect(html).toContain("login_required");
    expect(html).toContain("🔐");
  });

  it("includes data-failure-type attribute", () => {
    const job = { status: "failed", error: "CAPTCHA" };
    const html = renderFailureBadge(job);
    expect(html).toContain('data-failure-type="blocked"');
  });

  it("escapes HTML in content", () => {
    const job = { status: "failed", error: "<script>alert('xss')</script>" };
    const html = renderFailureBadge(job);
    expect(html).not.toContain("<script>");
    expect(html).toContain("unknown");
  });
});

// ─── renderFailurePanel ────────────────────────────────────────────────────

describe("renderFailurePanel()", () => {
  it("returns empty string for successful job", () => {
    const job = { status: "completed" };
    expect(renderFailurePanel(job)).toBe("");
  });

  it("returns full panel for failed job", () => {
    const job = { status: "failed", error: "CAPTCHA challenge", name: "Test Job" };
    const html = renderFailurePanel(job);
    expect(html).toContain("failure-panel");
    expect(html).toContain("Access Blocked");
    expect(html).toContain("What happened");
    expect(html).toContain("Recommended action");
  });

  it("includes technical details when error is present", () => {
    const job = { status: "error", error: "Specific error details here" };
    const html = renderFailurePanel(job);
    expect(html).toContain("Technical details");
    expect(html).toContain("Specific error details here");
  });

  it("hides technical details when no error message", () => {
    const job = { status: "failed", error: "" };
    const html = renderFailurePanel(job);
    expect(html).not.toContain("Technical details");
  });

  it("escapes HTML in error message", () => {
    const job = { status: "failed", error: "<script>alert('xss')</script>" };
    const html = renderFailurePanel(job);
    expect(html).not.toContain("<script>");
    expect(html).toContain("&lt;script&gt;");
  });
});

// ─── renderFailureTooltip ──────────────────────────────────────────────────

describe("renderFailureTooltip()", () => {
  it("returns empty string for successful job", () => {
    const job = { status: "completed" };
    expect(renderFailureTooltip(job)).toBe("");
  });

  it("returns tooltip for failed job", () => {
    const job = { status: "failed", error: "Timeout" };
    const html = renderFailureTooltip(job);
    expect(html).toContain("failure-tooltip");
    expect(html).toContain("Page Timed Out");
  });

  it("escapes HTML in tooltip content", () => {
    const job = { status: "failed", error: "<script>alert('xss')</script>" };
    const html = renderFailureTooltip(job);
    expect(html).not.toContain("<script>");
  });
});

// ─── initFailureBadges ─────────────────────────────────────────────────────

describe("initFailureBadges()", () => {
  it("does not throw when no badges exist", () => {
    expect(() => initFailureBadges()).not.toThrow();
  });

  it("attaches click handlers to badges", () => {
    document.body.innerHTML = `
      <div class="failure-badge" data-failure-type="blocked">
        <span class="failure-badge-icon">🛡️</span>
        <span class="failure-badge-text">Access Blocked</span>
      </div>
    `;
    initFailureBadges();
    const badge = document.querySelector(".failure-badge");
    expect(badge).toBeDefined();
    // Simulate click — should not throw
    expect(() => badge.click()).not.toThrow();
    document.body.innerHTML = "";
  });
});

// ─── attachFailureExplanationToJobRow ──────────────────────────────────────

describe("attachFailureExplanationToJobRow()", () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <div class="job-row" data-id="test-123">
        <div class="job-name-col">
          <div class="job-name">Test Job</div>
        </div>
        <div><span class="badge failed">Failed</span></div>
        <div class="job-actions">
          <button class="btn ghost small">View</button>
        </div>
      </div>
    `;
  });

  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("adds failure class to the row", () => {
    const row = document.querySelector(".job-row");
    const job = { id: "test-123", status: "failed", error: "Login required" };
    attachFailureExplanationToJobRow(row, job);
    expect(row.classList.contains("failure-login_required")).toBe(true);
  });

  it("does nothing for null row", () => {
    const job = { id: "test-123", status: "failed", error: "Login required" };
    expect(() => attachFailureExplanationToJobRow(null, job)).not.toThrow();
  });

  it("does nothing for null job", () => {
    const row = document.querySelector(".job-row");
    expect(() => attachFailureExplanationToJobRow(row, null)).not.toThrow();
  });

  it("does nothing for non-failed job", () => {
    const row = document.querySelector(".job-row");
    const job = { id: "test-123", status: "completed" };
    attachFailureExplanationToJobRow(row, job);
    expect(row.classList.contains("failure-")).toBe(false);
  });

  it("adds tooltip to failed badge", () => {
    const row = document.querySelector(".job-row");
    const job = { id: "test-123", status: "failed", error: "CAPTCHA" };
    attachFailureExplanationToJobRow(row, job);
    const badge = row.querySelector(".badge.failed");
    expect(badge.querySelector(".failure-inline-tooltip")).not.toBeNull();
  });
});
