/* ═══════════════════════════════════════════
   DataForge — Data Cleaning Assistant Tests
   ═══════════════════════════════════════════ */

import { describe, it, expect, beforeEach, afterEach } from "vitest";

// ─── Module Exports ───

describe("data-cleaning module exports", () => {
  it("exports detectFieldType", async () => {
    const mod = await import("./data-cleaning.js");
    expect(typeof mod.detectFieldType).toBe("function");
  });

  it("exports cleanValue", async () => {
    const mod = await import("./data-cleaning.js");
    expect(typeof mod.cleanValue).toBe("function");
  });

  it("exports wouldChange", async () => {
    const mod = await import("./data-cleaning.js");
    expect(typeof mod.wouldChange).toBe("function");
  });

  it("exports analyzeRows", async () => {
    const mod = await import("./data-cleaning.js");
    expect(typeof mod.analyzeRows).toBe("function");
  });

  it("exports applyCleaning", async () => {
    const mod = await import("./data-cleaning.js");
    expect(typeof mod.applyCleaning).toBe("function");
  });

  it("exports analyzeCleaning", async () => {
    const mod = await import("./data-cleaning.js");
    expect(typeof mod.analyzeCleaning).toBe("function");
  });

  it("exports renderCleaningPanel", async () => {
    const mod = await import("./data-cleaning.js");
    expect(typeof mod.renderCleaningPanel).toBe("function");
  });
});

// ─── detectFieldType ───

describe("detectFieldType", () => {
  it("returns 'text' for empty input", async () => {
    const { detectFieldType } = await import("./data-cleaning.js");
    expect(detectFieldType([])).toBe("text");
  });

  it("detects email type", async () => {
    const { detectFieldType } = await import("./data-cleaning.js");
    const values = ["a@b.com", "test@example.org", "user@domain.co.uk"];
    expect(detectFieldType(values)).toBe("email");
  });

  it("detects url type", async () => {
    const { detectFieldType } = await import("./data-cleaning.js");
    const values = ["https://example.com", "http://test.org/page", "https://a.co/path"];
    expect(detectFieldType(values)).toBe("url");
  });

  it("detects phone type", async () => {
    const { detectFieldType } = await import("./data-cleaning.js");
    const values = ["555-0100", "+1 555 5555", "(555) 123-4567"];
    expect(detectFieldType(values)).toBe("phone");
  });

  it("detects price type", async () => {
    const { detectFieldType } = await import("./data-cleaning.js");
    const values = ["$10.99", "€20.50", "1,234.56"];
    expect(detectFieldType(values)).toBe("price");
  });

  it("detects number type", async () => {
    const { detectFieldType } = await import("./data-cleaning.js");
    const values = ["42", "3.14", "1000"];
    expect(detectFieldType(values)).toBe("number");
  });

  it("detects date type", async () => {
    const { detectFieldType } = await import("./data-cleaning.js");
    const values = ["2024-01-15", "01/15/2024", "2024.01.15"];
    expect(detectFieldType(values)).toBe("date");
  });

  it("returns 'text' for mixed/unrecognized values", async () => {
    const { detectFieldType } = await import("./data-cleaning.js");
    const values = ["Hello", "World", "Some text here"];
    expect(detectFieldType(values)).toBe("text");
  });
});

// ─── cleanValue ───

describe("cleanValue", () => {
  it("normalizes email: lowercase + trim", async () => {
    const { cleanValue } = await import("./data-cleaning.js");
    expect(cleanValue("  User@Example.COM  ", "email")).toBe("user@example.com");
  });

  it("normalizes URL: removes tracking params", async () => {
    const { cleanValue } = await import("./data-cleaning.js");
    const url = "https://example.com/page?utm_source=test&foo=bar";
    const cleaned = cleanValue(url, "url");
    expect(cleaned).not.toContain("utm_source");
    expect(cleaned).toContain("foo=bar");
  });

  it("normalizes phone: extracts digits", async () => {
    const { cleanValue } = await import("./data-cleaning.js");
    expect(cleanValue("+1 (555) 123-4567", "phone")).toBe("15551234567");
  });

  it("normalizes price: removes currency symbols", async () => {
    const { cleanValue } = await import("./data-cleaning.js");
    expect(cleanValue("$10.99", "price")).toBe(10.99);
  });

  it("parses number from string", async () => {
    const { cleanValue } = await import("./data-cleaning.js");
    expect(cleanValue("  42  ", "number")).toBe(42);
  });

  it("normalizes date to YYYY-MM-DD", async () => {
    const { cleanValue } = await import("./data-cleaning.js");
    expect(cleanValue("01/15/2024", "date")).toBe("2024-01-15");
  });

  it("trims whitespace for text", async () => {
    const { cleanValue } = await import("./data-cleaning.js");
    expect(cleanValue("  Hello   World  ", "text")).toBe("Hello World");
  });

  it("passes through null/empty values", async () => {
    const { cleanValue } = await import("./data-cleaning.js");
    expect(cleanValue(null, "email")).toBeNull();
    expect(cleanValue("", "text")).toBe("");
    expect(cleanValue("—", "text")).toBe("—");
  });

  it("handles undefined value", async () => {
    const { cleanValue } = await import("./data-cleaning.js");
    expect(cleanValue(undefined, "text")).toBeUndefined();
  });
});

// ─── wouldChange ───

describe("wouldChange", () => {
  it("returns true when value would change", async () => {
    const { wouldChange } = await import("./data-cleaning.js");
    expect(wouldChange("  Hello  ", "text")).toBe(true);
  });

  it("returns false when value is already clean", async () => {
    const { wouldChange } = await import("./data-cleaning.js");
    expect(wouldChange("hello@example.com", "email")).toBe(false);
  });

  it("returns false for null/empty", async () => {
    const { wouldChange } = await import("./data-cleaning.js");
    expect(wouldChange(null, "text")).toBe(false);
    expect(wouldChange("", "text")).toBe(false);
  });
});

// ─── analyzeRows ───

describe("analyzeRows", () => {
  it("returns null for empty rows", async () => {
    const { analyzeRows } = await import("./data-cleaning.js");
    expect(analyzeRows([])).toBeNull();
  });

  it("detects fields and counts changes", async () => {
    const { analyzeRows } = await import("./data-cleaning.js");
    const rows = [
      { email: "  User@Example.COM  ", name: "John" },
      { email: "test@example.org", name: "Jane" },
    ];
    const result = analyzeRows(rows);
    expect(result).toBeDefined();
    expect(result.totalRows).toBe(2);
    expect(result.fields.length).toBeGreaterThanOrEqual(2);

    const emailField = result.fields.find((f) => f.name === "email");
    expect(emailField).toBeDefined();
    expect(emailField.type).toBe("email");
    expect(emailField.wouldChange).toBe(1); // one email has whitespace
  });

  it("skips meta fields (_ prefix)", async () => {
    const { analyzeRows } = await import("./data-cleaning.js");
    const rows = [{ email: "a@b.com", _meta: "should-skip" }];
    const result = analyzeRows(rows);
    expect(result.fields.find((f) => f.name === "_meta")).toBeUndefined();
  });

  it("provides sample changes", async () => {
    const { analyzeRows } = await import("./data-cleaning.js");
    const rows = [{ email: "  UPPER@EXAMPLE.COM  ", name: "Clean" }];
    const result = analyzeRows(rows);
    const emailField = result.fields.find((f) => f.name === "email");
    expect(emailField.samples).toBeDefined();
    expect(emailField.samples.original).toContain("  ");
    expect(emailField.samples.cleaned).toBe("upper@example.com");
  });
});

// ─── applyCleaning ───

describe("applyCleaning", () => {
  it("applies cleaning to all rows", async () => {
    const { analyzeRows, applyCleaning } = await import("./data-cleaning.js");
    const rows = [
      { email: "  User@Example.COM  ", name: "John" },
      { email: "test@example.org", name: "  Jane  " },
    ];
    analyzeRows(rows);
    const cleaned = applyCleaning(rows);
    expect(cleaned[0].email).toBe("user@example.com");
    expect(cleaned[1].name).toBe("Jane");
  });

  it("preserves rows that don't change", async () => {
    const { analyzeRows, applyCleaning } = await import("./data-cleaning.js");
    const rows = [{ email: "user@example.com", name: "Jane" }];
    analyzeRows(rows);
    const cleaned = applyCleaning(rows);
    expect(cleaned[0].email).toBe("user@example.com");
    expect(cleaned[0].name).toBe("Jane");
  });

  it("handles null analysis state", async () => {
    const mod = await import("./data-cleaning.js");
    mod.clearCleaningState(); // ensure clean state
    const rows = [{ email: "  User@Example.COM  " }];
    const cleaned = mod.applyCleaning(rows);
    expect(cleaned).toBe(rows); // returns original when state is null
  });
});

// ─── State Management ───

describe("state management", () => {
  it("clearCleaningState resets state", async () => {
    const { analyzeRows, clearCleaningState, getCleaningState } = await import("./data-cleaning.js");
    analyzeRows([{ email: "  A@B.COM  " }]);
    expect(getCleaningState()).not.toBeNull();
    clearCleaningState();
    expect(getCleaningState()).toBeNull();
  });
});

// ─── HTML Structure ───

describe("cleaning panel HTML structure", () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <div id="cleaning-panel" class="hidden"></div>
    `;
  });

  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("has the cleaning panel container", () => {
    const panel = document.getElementById("cleaning-panel");
    expect(panel).toBeDefined();
    expect(panel.classList.contains("hidden")).toBe(true);
  });

  it("renders summary when changes exist", async () => {
    const { analyzeRows, renderCleaningPanel } = await import("./data-cleaning.js");
    analyzeRows([{ email: "  User@Example.COM  " }]);
    renderCleaningPanel();
    const panel = document.getElementById("cleaning-panel");
    expect(panel.classList.contains("hidden")).toBe(false);
    expect(panel.textContent).toContain("Data Cleaning");
  });

  it("hides panel when no changes exist", async () => {
    const { analyzeRows, renderCleaningPanel } = await import("./data-cleaning.js");
    analyzeRows([{ email: "user@example.com", name: "Clean" }]);
    renderCleaningPanel();
    const panel = document.getElementById("cleaning-panel");
    expect(panel.classList.contains("hidden")).toBe(true);
  });

  it("shows apply and hide buttons", async () => {
    const { analyzeRows, renderCleaningPanel } = await import("./data-cleaning.js");
    analyzeRows([{ email: "  A@B.COM  " }]);
    renderCleaningPanel();
    expect(document.querySelector('[data-action="apply-cleaning"]')).toBeDefined();
    expect(document.querySelector('[data-action="hide-cleaning-panel"]')).toBeDefined();
  });

  it("shows field type badge", async () => {
    const { analyzeRows, renderCleaningPanel } = await import("./data-cleaning.js");
    analyzeRows([{ email: "  A@B.COM  " }]);
    renderCleaningPanel();
    const typeBadge = document.querySelector(".cleaning-field-type");
    expect(typeBadge).toBeDefined();
    expect(typeBadge.textContent).toContain("email");
  });

  it("shows sample before/after values", async () => {
    const { analyzeRows, renderCleaningPanel } = await import("./data-cleaning.js");
    analyzeRows([{ email: "  UPPER@EXAMPLE.COM  " }]);
    renderCleaningPanel();
    const oldSample = document.querySelector(".cleaning-sample-old");
    const newSample = document.querySelector(".cleaning-sample-new");
    expect(oldSample).toBeDefined();
    expect(newSample).toBeDefined();
    expect(newSample.textContent).toContain("upper@example.com");
  });
});
