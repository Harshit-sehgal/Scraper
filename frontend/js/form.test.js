/* ═══════════════════════════════════════════
   DataForge — Job Form Tests
   ═══════════════════════════════════════════ */

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { addField, addFilter, onFilterOpChange } from "./form.js";

// ─── Setup / Teardown ──────────────────────────────────────────────────────

beforeEach(() => {
  document.body.innerHTML = `
    <div id="schema-container"></div>
    <div id="filters-container"></div>
  `;
});

afterEach(() => {
  document.body.innerHTML = "";
});

// ─── addField ───────────────────────────────────────────────────────────────

describe("addField()", () => {
  it("adds a field row to schema-container", () => {
    addField();
    const rows = document.querySelectorAll(".field-row");
    expect(rows.length).toBe(1);
  });

  it("increments field count on each call", () => {
    addField();
    addField();
    addField();
    expect(document.querySelectorAll(".field-row").length).toBe(3);
  });

  it("sets name from preset", () => {
    addField({ name: "company_name", field_type: "string", description: "Company name" });
    const input = document.querySelector(".sf-name");
    expect(input.value).toBe("company_name");
  });

  it("sets description from preset", () => {
    addField({ description: "Star rating out of 5" });
    const input = document.querySelector(".sf-desc");
    expect(input.value).toBe("Star rating out of 5");
  });

  it("sets field type from preset", () => {
    addField({ field_type: "integer" });
    const select = document.querySelector(".sf-type");
    expect(select.value).toBe("integer");
  });

  it("defaults to string type when not in preset", () => {
    addField({ name: "test" });
    const select = document.querySelector(".sf-type");
    expect(select.value).toBe("string");
  });

  it("includes a remove button", () => {
    addField();
    const btn = document.querySelector(".btn-x");
    expect(btn).not.toBeNull();
    expect(btn.getAttribute("data-action")).toBe("remove-field");
  });

  it("escapes HTML in preset name and description", () => {
    addField({ name: "<script>alert('xss')</script>", description: "<b>bold</b>" });
    const nameInput = document.querySelector(".sf-name");
    const descInput = document.querySelector(".sf-desc");
    // Input values are set via .value = esc(name), so the escaped text
    // becomes the literal value attribute in innerHTML, then the browser
    // decodes it when setting .value from the attribute.
    expect(nameInput.value).toBe("<script>alert('xss')</script>");
    expect(descInput.value).toBe("<b>bold</b>");
  });
});

// ─── addFilter ─────────────────────────────────────────────────────────────

describe("addFilter()", () => {
  it("adds a filter row to filters-container", () => {
    addFilter();
    const rows = document.querySelectorAll(".filter-row");
    expect(rows.length).toBe(1);
  });

  it("increments filter count on each call", () => {
    addFilter();
    addFilter();
    addFilter();
    expect(document.querySelectorAll(".filter-row").length).toBe(3);
  });

  it("includes field select, operator select, value input, and remove button", () => {
    addFilter();
    const row = document.querySelector(".filter-row");
    expect(row.querySelector(".ff-field")).not.toBeNull();
    expect(row.querySelector(".ff-op")).not.toBeNull();
    expect(row.querySelector(".ff-value")).not.toBeNull();
    expect(row.querySelector(".btn-x")).not.toBeNull();
  });

  it("populates field options from schema field names", () => {
    // Add some schema fields first
    const container = document.getElementById("schema-container");
    container.innerHTML = `
      <div class="field-row">
        <input class="sf-name" value="name" />
      </div>
      <div class="field-row">
        <input class="sf-name" value="email" />
      </div>
    `;
    addFilter();
    const select = document.querySelector(".ff-field");
    expect(select.innerHTML).toContain("name");
    expect(select.innerHTML).toContain("email");
  });

  it("shows placeholder when no schema fields exist", () => {
    addFilter();
    const select = document.querySelector(".ff-field");
    expect(select.innerHTML).toContain("—");
  });
});

// ─── onFilterOpChange ──────────────────────────────────────────────────────

describe("onFilterOpChange()", () => {
  beforeEach(() => {
    const container = document.getElementById("filters-container");
    container.innerHTML = `
      <div class="filter-row">
        <div class="form-group ff-value-group">
          <label>Value</label>
          <input class="ff-value" value="" />
        </div>
        <button class="btn-x">✕</button>
      </div>
    `;
  });

  it("adds distance extra fields when operator is distance_within", () => {
    const sel = document.createElement("select");
    sel.innerHTML = `<option value="distance_within">Distance</option><option value="equals">Equals</option>`;
    sel.value = "distance_within";
    // Attach to row
    const row = document.querySelector(".filter-row");
    row.prepend(sel);

    onFilterOpChange(sel);

    expect(row.classList.contains("has-distance")).toBe(true);
    expect(row.querySelectorAll(".dist-extra").length).toBe(2);
    expect(row.querySelector(".ff-value-group label").textContent).toBe("Max km/mi");
    // Origin address and unit inputs should exist
    expect(row.querySelector(".ff-origin")).not.toBeNull();
    expect(row.querySelector(".ff-unit")).not.toBeNull();
  });

  it("removes distance extras when switching from distance to another operator", () => {
    const sel = document.createElement("select");
    sel.innerHTML = `<option value="distance_within">Distance</option><option value="equals">Equals</option>`;
    sel.value = "distance_within";
    const row = document.querySelector(".filter-row");
    row.prepend(sel);

    onFilterOpChange(sel);

    // Verify extras were added first
    expect(row.querySelectorAll(".dist-extra").length).toBe(2);

    // Now switch away
    sel.value = "equals";
    onFilterOpChange(sel);

    expect(row.classList.contains("has-distance")).toBe(false);
    expect(row.querySelectorAll(".dist-extra").length).toBe(0);
    expect(row.querySelector(".ff-value-group label").textContent).toBe("Value");
  });

  it("does not add extras for non-distance operators", () => {
    const sel = document.createElement("select");
    sel.innerHTML = `<option value="contains">Contains</option><option value="equals">Equals</option>`;
    sel.value = "contains";
    const row = document.querySelector(".filter-row");
    row.prepend(sel);

    onFilterOpChange(sel);

    expect(row.classList.contains("has-distance")).toBe(false);
    expect(row.querySelectorAll(".dist-extra").length).toBe(0);
  });
});
