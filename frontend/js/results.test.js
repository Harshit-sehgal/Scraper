/* ═══════════════════════════════════════════
   DataForge — Results Tests
   ═══════════════════════════════════════════ */

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { renderLogs, applyResultSearch, renderTable, renderPaginationControls, paginateRows, formatPaginationLabel, getCurrentPage, getPageSize } from "./results.js";

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

// ─── paginateRows ──────────────────────────────────────────────────────────

describe("paginateRows()", () => {
  const rows = Array.from({ length: 73 }, (_, i) => ({ id: i + 1, name: `Row ${i + 1}` }));

  it("returns first page of rows", () => {
    const result = paginateRows(rows, 1, 25);
    expect(result.rows).toHaveLength(25);
    expect(result.rows[0].id).toBe(1);
    expect(result.totalPages).toBe(3);
    expect(result.totalRows).toBe(73);
    expect(result.currentPage).toBe(1);
  });

  it("returns second page of rows", () => {
    const result = paginateRows(rows, 2, 25);
    expect(result.rows).toHaveLength(25);
    expect(result.rows[0].id).toBe(26);
    expect(result.currentPage).toBe(2);
  });

  it("returns third (last) page with remaining rows", () => {
    const result = paginateRows(rows, 3, 25);
    expect(result.rows).toHaveLength(23);
    expect(result.rows[0].id).toBe(51);
    expect(result.currentPage).toBe(3);
  });

  it("clamps page to 1 when page < 1", () => {
    const result = paginateRows(rows, 0, 25);
    expect(result.currentPage).toBe(1);
    expect(result.rows[0].id).toBe(1);
  });

  it("clamps page to last page when page exceeds total", () => {
    const result = paginateRows(rows, 99, 25);
    expect(result.currentPage).toBe(3);
    expect(result.rows).toHaveLength(23);
  });

  it("handles empty array", () => {
    const result = paginateRows([], 1, 25);
    expect(result.rows).toHaveLength(0);
    expect(result.totalPages).toBe(1);
    expect(result.currentPage).toBe(1);
  });

  it("handles custom page size", () => {
    const result = paginateRows(rows, 1, 50);
    expect(result.rows).toHaveLength(50);
    expect(result.rows[0].id).toBe(1);
    expect(result.rows[49].id).toBe(50);
    expect(result.totalPages).toBe(2);
  });

  it("handles single record", () => {
    const result = paginateRows([{ id: 1 }], 1, 25);
    expect(result.rows).toHaveLength(1);
    expect(result.totalPages).toBe(1);
  });

  it("handles exact multiple", () => {
    const exactRows = Array.from({ length: 50 }, (_, i) => ({ id: i + 1 }));
    const result = paginateRows(exactRows, 2, 25);
    expect(result.rows).toHaveLength(25);
    expect(result.rows[0].id).toBe(26);
    expect(result.totalPages).toBe(2);
  });
});

// ─── formatPaginationLabel ───────────────────────────────────────────────────

describe("formatPaginationLabel()", () => {
  it("formats first page correctly", () => {
    expect(formatPaginationLabel(1, 25, 73)).toBe("1–25 of 73");
  });

  it("formats second page correctly", () => {
    expect(formatPaginationLabel(2, 25, 73)).toBe("26–50 of 73");
  });

  it("formats last page with fewer rows", () => {
    expect(formatPaginationLabel(3, 25, 73)).toBe("51–73 of 73");
  });

  it("formats single row", () => {
    expect(formatPaginationLabel(1, 25, 1)).toBe("1–1 of 1");
  });

  it("formats exact page boundary", () => {
    expect(formatPaginationLabel(2, 25, 50)).toBe("26–50 of 50");
  });

  it("handles custom page size", () => {
    expect(formatPaginationLabel(1, 100, 250)).toBe("1–100 of 250");
  });
});

// ─── State Accessors ────────────────────────────────────────────────────────

describe("pagination state accessors", () => {
  it("getCurrentPage returns initial page (1)", () => {
    expect(getCurrentPage()).toBe(1);
  });

  it("getPageSize returns default page size (25)", () => {
    expect(getPageSize()).toBe(25);
  });
});

// ─── renderPaginationControls (integration check) ───────────────────────────

describe("renderPaginationControls()", () => {
  beforeEach(() => {
    const container = document.createElement("div");
    container.id = "pagination-controls";
    document.body.appendChild(container);
  });

  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("shows simple info when only one page", () => {
    renderPaginationControls(1, 1, 10);
    const container = document.getElementById("pagination-controls");
    expect(container.textContent).toContain("10 rows");
    expect(container.classList.contains("has-pages")).toBe(false);
  });
});
