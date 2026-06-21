/* ═══════════════════════════════════════════
   DataForge — Duplicate Detection Tests
   ═══════════════════════════════════════════ */

import { describe, it, expect, beforeEach, afterEach } from "vitest";

// ─── Module Exports ───

describe("duplicate-detection module exports", () => {
  it("exports fingerprintRow", async () => {
    const mod = await import("./duplicate-detection.js");
    expect(typeof mod.fingerprintRow).toBe("function");
  });

  it("exports detectDuplicates", async () => {
    const mod = await import("./duplicate-detection.js");
    expect(typeof mod.detectDuplicates).toBe("function");
  });

  it("exports getDuplicateIndices", async () => {
    const mod = await import("./duplicate-detection.js");
    expect(typeof mod.getDuplicateIndices).toBe("function");
  });

  it("exports findDuplicates", async () => {
    const mod = await import("./duplicate-detection.js");
    expect(typeof mod.findDuplicates).toBe("function");
  });

  it("exports removeDuplicates", async () => {
    const mod = await import("./duplicate-detection.js");
    expect(typeof mod.removeDuplicates).toBe("function");
  });

  it("exports clearDuplicateState", async () => {
    const mod = await import("./duplicate-detection.js");
    expect(typeof mod.clearDuplicateState).toBe("function");
  });

  it("exports getDuplicateState", async () => {
    const mod = await import("./duplicate-detection.js");
    expect(typeof mod.getDuplicateState).toBe("function");
  });

  it("exports renderDuplicateSummary", async () => {
    const mod = await import("./duplicate-detection.js");
    expect(typeof mod.renderDuplicateSummary).toBe("function");
  });
});

// ─── fingerprintRow ───

describe("fingerprintRow", () => {
  it("returns empty string for null/undefined input", async () => {
    const { fingerprintRow } = await import("./duplicate-detection.js");
    expect(fingerprintRow(null)).toBe("");
    expect(fingerprintRow(undefined)).toBe("");
  });

  it("fingerprints a row with specified key fields", async () => {
    const { fingerprintRow } = await import("./duplicate-detection.js");
    const row = { name: "Acme Corp", email: "acme@example.com", phone: "555-0100" };
    const fp = fingerprintRow(row, ["name", "email"]);
    expect(fp).toBe("acme corp|acme@example.com");
  });

  it("handles missing key fields gracefully", async () => {
    const { fingerprintRow } = await import("./duplicate-detection.js");
    const row = { name: "Test", email: "" };
    const fp = fingerprintRow(row, ["name", "email"]);
    expect(fp).toBe("test|");
  });

  it("auto-detects fields when keyFields is empty", async () => {
    const { fingerprintRow } = await import("./duplicate-detection.js");
    const row = { name: "Test", email: "t@t.com", phone: "123", _meta: "skip" };
    const fp = fingerprintRow(row, []);
    expect(fp).toContain("name:test");
    expect(fp).toContain("email:t@t.com");
    expect(fp).not.toContain("_meta");
  });

  it("handles object and array values", async () => {
    const { fingerprintRow } = await import("./duplicate-detection.js");
    const row = { tags: ["a", "b"], meta: { key: "val" } };
    const fp = fingerprintRow(row, ["tags", "meta"]);
    expect(fp).toBe('a, b|{"key":"val"}');
  });

  it("is case-insensitive", async () => {
    const { fingerprintRow } = await import("./duplicate-detection.js");
    const fp1 = fingerprintRow({ name: "Acme Corp" }, ["name"]);
    const fp2 = fingerprintRow({ name: "acme corp" }, ["name"]);
    expect(fp1).toBe(fp2);
  });

  it("trims whitespace in fingerprint", async () => {
    const { fingerprintRow } = await import("./duplicate-detection.js");
    const fp = fingerprintRow({ name: "  Acme Corp  " }, ["name"]);
    expect(fp).toBe("acme corp");
  });
});

// ─── detectDuplicates ───

describe("detectDuplicates", () => {
  it("returns empty state for empty rows", async () => {
    const { detectDuplicates } = await import("./duplicate-detection.js");
    const result = detectDuplicates([], ["name"]);
    expect(result.groups).toEqual([]);
    expect(result.dupCount).toBe(0);
  });

  it("detects duplicates by specified key field", async () => {
    const { detectDuplicates } = await import("./duplicate-detection.js");
    const rows = [
      { name: "Acme Corp", email: "a@a.com" },
      { name: "Acme Corp", email: "b@b.com" },
      { name: "Beta Inc", email: "c@c.com" },
    ];
    const result = detectDuplicates(rows, ["name"]);
    expect(result.groups.length).toBe(1);
    expect(result.dupCount).toBe(1);
    expect(result.totalRows).toBe(3);
  });

  it("detects multiple duplicate groups", async () => {
    const { detectDuplicates } = await import("./duplicate-detection.js");
    const rows = [
      { name: "A", email: "a@a.com" },
      { name: "A", email: "a2@a.com" },
      { name: "B", email: "b@b.com" },
      { name: "B", email: "b2@b.com" },
    ];
    const result = detectDuplicates(rows, ["name"]);
    expect(result.groups.length).toBe(2);
    expect(result.dupCount).toBe(2);
  });

  it("keeps the most complete row in each group", async () => {
    const { detectDuplicates } = await import("./duplicate-detection.js");
    const rows = [
      { name: "A", email: "", phone: "" },
      { name: "A", email: "a@a.com", phone: "123" },
    ];
    const result = detectDuplicates(rows, ["name"]);
    expect(result.groups[0].kept).toBe(1); // second row has more data
  });

  it("returns no duplicates for unique rows", async () => {
    const { detectDuplicates } = await import("./duplicate-detection.js");
    const rows = [
      { name: "A", email: "a@a.com" },
      { name: "B", email: "b@b.com" },
    ];
    const result = detectDuplicates(rows, ["name"]);
    expect(result.groups.length).toBe(0);
    expect(result.dupCount).toBe(0);
  });
});

// ─── getDuplicateIndices ───

describe("getDuplicateIndices", () => {
  it("returns empty set when no duplicates detected", async () => {
    const { detectDuplicates, getDuplicateIndices } = await import("./duplicate-detection.js");
    detectDuplicates([{ name: "A" }], ["name"]);
    const indices = getDuplicateIndices();
    expect(indices.size).toBe(0);
  });

  it("returns indices of duplicate rows (excluding kept)", async () => {
    const { detectDuplicates, getDuplicateIndices } = await import("./duplicate-detection.js");
    const rows = [
      { name: "A", email: "" },
      { name: "A", email: "a@a.com" },
      { name: "B", email: "b@b.com" },
    ];
    detectDuplicates(rows, ["name"]);
    const indices = getDuplicateIndices();
    // Row 1 (index 1) has more data so kept=1, row 0 is duplicate
    expect(indices.size).toBe(1);
    expect(indices.has(0)).toBe(true);
  });
});

// ─── State Management ───

describe("state management", () => {
  it("clearDuplicateState resets state", async () => {
    const { detectDuplicates, clearDuplicateState, getDuplicateState } = await import("./duplicate-detection.js");
    detectDuplicates([{ name: "A" }, { name: "A" }], ["name"]);
    expect(getDuplicateState().dupCount).toBe(1);
    clearDuplicateState();
    expect(getDuplicateState()).toBeNull();
  });

  it("getDuplicateState returns current state", async () => {
    const { detectDuplicates, getDuplicateState } = await import("./duplicate-detection.js");
    const result = detectDuplicates([{ name: "A" }], ["name"]);
    expect(getDuplicateState()).toBe(result);
  });
});

// ─── HTML Structure ───

describe("duplicate panel HTML structure", () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <div id="dup-panel" class="hidden"></div>
    `;
  });

  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("has the duplicate panel container", () => {
    const panel = document.getElementById("dup-panel");
    expect(panel).toBeDefined();
    expect(panel.classList.contains("hidden")).toBe(true);
  });

  it("renders summary when state exists", async () => {
    const { detectDuplicates, renderDuplicateSummary } = await import("./duplicate-detection.js");
    detectDuplicates([{ name: "A" }, { name: "A" }], ["name"]);
    renderDuplicateSummary();
    const panel = document.getElementById("dup-panel");
    expect(panel.classList.contains("hidden")).toBe(false);
    expect(panel.textContent).toContain("Duplicates Found");
    expect(panel.textContent).toContain("1 duplicate");
  });

  it("hides panel when no duplicates exist", async () => {
    const { detectDuplicates, renderDuplicateSummary } = await import("./duplicate-detection.js");
    detectDuplicates([{ name: "A" }, { name: "B" }], ["name"]);
    renderDuplicateSummary();
    const panel = document.getElementById("dup-panel");
    expect(panel.classList.contains("hidden")).toBe(true);
  });

  it("shows remove duplicates button", async () => {
    const { detectDuplicates, renderDuplicateSummary } = await import("./duplicate-detection.js");
    detectDuplicates([{ name: "A" }, { name: "A" }], ["name"]);
    renderDuplicateSummary();
    const btn = document.querySelector('[data-action="remove-duplicates"]');
    expect(btn).toBeDefined();
    expect(btn.textContent).toContain("Remove");
  });

  it("shows hide button", async () => {
    const { detectDuplicates, renderDuplicateSummary } = await import("./duplicate-detection.js");
    detectDuplicates([{ name: "A" }, { name: "A" }], ["name"]);
    renderDuplicateSummary();
    const btn = document.querySelector('[data-action="hide-duplicate-panel"]');
    expect(btn).toBeDefined();
    expect(btn.textContent).toContain("Hide");
  });

  it("renders group rows for each duplicate group", async () => {
    const { detectDuplicates, renderDuplicateSummary } = await import("./duplicate-detection.js");
    detectDuplicates([{ name: "A" }, { name: "A" }, { name: "B" }, { name: "B" }], ["name"]);
    renderDuplicateSummary();
    const groupRows = document.querySelectorAll(".dup-group-row");
    expect(groupRows.length).toBe(2);
  });

  it("shows kept badge for each group row", async () => {
    const { detectDuplicates, renderDuplicateSummary } = await import("./duplicate-detection.js");
    detectDuplicates([{ name: "A" }, { name: "A" }], ["name"]);
    renderDuplicateSummary();
    const keptBadge = document.querySelector(".dup-group-kept-badge");
    expect(keptBadge).toBeDefined();
    expect(keptBadge.textContent).toContain("kept");
  });
});

// ─── Fingerprint Consistency ───

describe("fingerprint consistency", () => {
  it("identical rows produce identical fingerprints", async () => {
    const { fingerprintRow } = await import("./duplicate-detection.js");
    const row1 = { name: "Foo", email: "foo@bar.com" };
    const row2 = { name: "Foo", email: "foo@bar.com" };
    expect(fingerprintRow(row1, ["name", "email"])).toBe(fingerprintRow(row2, ["name", "email"]));
  });

  it("different rows produce different fingerprints", async () => {
    const { fingerprintRow } = await import("./duplicate-detection.js");
    const row1 = { name: "Foo", email: "foo@bar.com" };
    const row2 = { name: "Bar", email: "bar@foo.com" };
    expect(fingerprintRow(row1, ["name", "email"])).not.toBe(fingerprintRow(row2, ["name", "email"]));
  });

  it("whitespace does not affect fingerprint match", async () => {
    const { fingerprintRow } = await import("./duplicate-detection.js");
    const fp1 = fingerprintRow({ name: "  Hello World  " }, ["name"]);
    const fp2 = fingerprintRow({ name: "hello world" }, ["name"]);
    expect(fp1).toBe(fp2);
  });
});
