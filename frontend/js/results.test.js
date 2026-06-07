/* ═══════════════════════════════════════════
   DataForge — Results Tests
   ═══════════════════════════════════════════ */

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { renderLogs, applyResultSearch, renderTable } from "./results.js";

// ─── renderLogs ────────────────────────────────────────────────────────────

describe("renderLogs()", () => {
  beforeEach(() => {
    const container = document.createElement("div");
    container.id = "logs-container";
    document.body.appendChild(container);
  });

  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("renders log entries sorted by timestamp", () => {
    renderLogs([
      { timestamp: "2026-01-03T00:00:00Z", message: "third", level: "info" },
      { timestamp: "2026-01-01T00:00:00Z", message: "first", level: "info" },
      { timestamp: "2026-01-02T00:00:00Z", message: "second", level: "info" },
    ]);
    const container = document.getElementById("logs-container");
    const entries = container.querySelectorAll(".log-entry");
    expect(entries.length).toBe(3);
    expect(entries[0].textContent).toContain("first");
    expect(entries[1].textContent).toContain("second");
    expect(entries[2].textContent).toContain("third");
  });

  it("renders log level as a CSS class", () => {
    renderLogs([{ timestamp: "2026-01-01T00:00:00Z", message: "error occurred", level: "error" }]);
    const container = document.getElementById("logs-container");
    const msgSpan = container.querySelector(".log-msg");
    expect(msgSpan.className).toContain("error");
    expect(msgSpan.textContent).toContain("error occurred");
  });

  it("filters out logs with invalid timestamps", () => {
    renderLogs([
      { timestamp: "2026-01-01T00:00:00Z", message: "valid", level: "info" },
      { timestamp: "not-a-date", message: "invalid", level: "info" },
      { timestamp: null, message: "null-ts", level: "info" },
    ]);
    const container = document.getElementById("logs-container");
    const entries = container.querySelectorAll(".log-entry");
    expect(entries.length).toBe(1);
    expect(entries[0].textContent).toContain("valid");
    expect(entries[0].textContent).not.toContain("invalid");
  });

  it("handles empty log array", () => {
    renderLogs([]);
    const container = document.getElementById("logs-container");
    expect(container.innerHTML).toBe("");
  });

  it("escapes HTML in log messages", () => {
    renderLogs([{ timestamp: "2026-01-01T00:00:00Z", message: "<script>alert('xss')</script>", level: "info" }]);
    const container = document.getElementById("logs-container");
    expect(container.innerHTML).toContain("&lt;script&gt;");
    expect(container.innerHTML).not.toContain("<script>");
  });
});

// ─── applyResultSearch ──────────────────────────────────────────────────────

describe("applyResultSearch()", () => {
  const rows = [
    { company_name: "Alpha Corp", email: "alpha@example.com", phone: "555-0101" },
    { company_name: "Beta Inc", email: "beta@example.com", phone: "555-0202" },
    { company_name: "Gamma LLC", email: "gamma@test.org", phone: "555-0303" },
  ];

  beforeEach(() => {
    const input = document.createElement("input");
    input.id = "inp-result-search";
    input.value = "";
    document.body.appendChild(input);
  });

  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("returns all rows when no search query", () => {
    expect(applyResultSearch(rows)).toHaveLength(3);
  });

  it("filters by company name", () => {
    document.getElementById("inp-result-search").value = "alpha";
    const result = applyResultSearch(rows);
    expect(result).toHaveLength(1);
    expect(result[0].company_name).toBe("Alpha Corp");
  });

  it("filters by email domain", () => {
    document.getElementById("inp-result-search").value = "test.org";
    const result = applyResultSearch(rows);
    expect(result).toHaveLength(1);
    expect(result[0].company_name).toBe("Gamma LLC");
  });

  it("is case-insensitive", () => {
    document.getElementById("inp-result-search").value = "BETA";
    const result = applyResultSearch(rows);
    expect(result).toHaveLength(1);
  });

  it("returns empty array when no match", () => {
    document.getElementById("inp-result-search").value = "nonexistent";
    expect(applyResultSearch(rows)).toHaveLength(0);
  });

  it("searches through array values", () => {
    const rowsWithArrays = [{ tags: ["alpha", "beta", "gamma"], name: "Multi" }];
    document.getElementById("inp-result-search").value = "gamma";
    const result = applyResultSearch(rowsWithArrays);
    expect(result).toHaveLength(1);
  });
});

// ─── renderTable ────────────────────────────────────────────────────────────

describe("renderTable()", () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <table>
        <thead id="res-thead"></thead>
        <tbody id="res-tbody"></tbody>
      </table>
    `;
  });

  it("renders header row from keys", () => {
    renderTable([{ name: "Test", value: "123" }]);
    const thead = document.getElementById("res-thead");
    expect(thead.innerHTML).toContain("name");
    expect(thead.innerHTML).toContain("value");
  });

  it("renders data rows", () => {
    renderTable([{ name: "Test", value: "123" }]);
    const tbody = document.getElementById("res-tbody");
    expect(tbody.innerHTML).toContain("Test");
    expect(tbody.innerHTML).toContain("123");
  });

  it("shows empty message when no results", () => {
    renderTable([], "Nothing here");
    const tbody = document.getElementById("res-tbody");
    expect(tbody.innerHTML).toContain("Nothing here");
  });

  it("prefers preferred column order", () => {
    renderTable([{ value: "v", company_name: "ACME", email: "a@b.com" }]);
    const thead = document.getElementById("res-thead");
    const html = thead.innerHTML;
    const idxCompany = html.indexOf("company_name");
    const idxEmail = html.indexOf("email");
    const idxValue = html.indexOf("value");
    // company_name and email should appear before value
    expect(idxCompany).toBeLessThan(idxValue);
    expect(idxEmail).toBeLessThan(idxValue);
  });

  it("converts null values to em dash", () => {
    renderTable([{ name: null, value: "present" }]);
    const tbody = document.getElementById("res-tbody");
    expect(tbody.innerHTML).toContain("\u2014");
    expect(tbody.innerHTML).toContain("present");
  });

  it("skips keys starting with underscore", () => {
    renderTable([{ name: "Test", _hidden: "secret", value: "123" }]);
    const thead = document.getElementById("res-thead");
    expect(thead.innerHTML).toContain("name");
    expect(thead.innerHTML).toContain("value");
    expect(thead.innerHTML).not.toContain("_hidden");
  });
});
