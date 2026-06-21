/* ═══════════════════════════════════════════
   DataForge — Data Profile Summary Tests
   ═══════════════════════════════════════════ */

import { describe, it, expect, beforeEach, afterEach } from "vitest";

// ─── Module Exports ───

describe("data-profile module exports", () => {
  it("exports generateProfile", async () => {
    const mod = await import("./data-profile.js");
    expect(typeof mod.generateProfile).toBe("function");
  });

  it("exports showDataProfile", async () => {
    const mod = await import("./data-profile.js");
    expect(typeof mod.showDataProfile).toBe("function");
  });

  it("exports renderProfilePanel", async () => {
    const mod = await import("./data-profile.js");
    expect(typeof mod.renderProfilePanel).toBe("function");
  });

  it("exports getProfileState", async () => {
    const mod = await import("./data-profile.js");
    expect(typeof mod.getProfileState).toBe("function");
  });
});

// ─── generateProfile ───

describe("generateProfile", () => {
  it("returns null for empty rows", async () => {
    const { generateProfile } = await import("./data-profile.js");
    expect(generateProfile([])).toBeNull();
  });

  it("generates profile with correct row count", async () => {
    const { generateProfile } = await import("./data-profile.js");
    const rows = [
      { name: "A", email: "a@a.com" },
      { name: "B", email: "b@b.com" },
      { name: "C", email: "c@c.com" },
    ];
    const profile = generateProfile(rows);
    expect(profile.totalRows).toBe(3);
    expect(profile.totalFields).toBe(2);
  });

  it("skips meta fields (_ prefix)", async () => {
    const { generateProfile } = await import("./data-profile.js");
    const rows = [{ name: "A", _hidden: "secret" }];
    const profile = generateProfile(rows);
    expect(profile.fields.find((f) => f.name === "_hidden")).toBeUndefined();
    expect(profile.fields.find((f) => f.name === "name")).toBeDefined();
  });

  it("counts non-empty and empty values correctly", async () => {
    const { generateProfile } = await import("./data-profile.js");
    const rows = [{ email: "a@a.com" }, { email: "" }, { email: null }, { email: "—" }];
    const profile = generateProfile(rows);
    const emailField = profile.fields.find((f) => f.name === "email");
    expect(emailField.nonEmpty).toBe(1);
    expect(emailField.empty).toBe(3);
  });

  it("computes fill rate percentages", async () => {
    const { generateProfile } = await import("./data-profile.js");
    const rows = [{ name: "A" }, { name: "B" }, { name: "" }];
    const profile = generateProfile(rows);
    const nameField = profile.fields.find((f) => f.name === "name");
    expect(nameField.fillRate).toBe(67); // 2/3 = 66.6 -> 67
  });

  it("counts unique values", async () => {
    const { generateProfile } = await import("./data-profile.js");
    const rows = [{ color: "red" }, { color: "blue" }, { color: "red" }];
    const profile = generateProfile(rows);
    const colorField = profile.fields.find((f) => f.name === "color");
    expect(colorField.uniqueValues).toBe(2); // red, blue
  });

  it("returns sample values (up to 3)", async () => {
    const { generateProfile } = await import("./data-profile.js");
    const rows = [{ tag: "a" }, { tag: "b" }, { tag: "c" }, { tag: "d" }];
    const profile = generateProfile(rows);
    const tagField = profile.fields.find((f) => f.name === "tag");
    expect(tagField.sampleValues.length).toBeLessThanOrEqual(3);
    expect(tagField.sampleValues[0]).toBe("a");
  });

  it("counts empty fields (all rows empty for that field)", async () => {
    const { generateProfile } = await import("./data-profile.js");
    const rows = [
      { name: "A", notes: "" },
      { name: "B", notes: null },
    ];
    const profile = generateProfile(rows);
    expect(profile.emptyFields).toBe(1); // notes is all empty
  });

  it("reports data types found in each field", async () => {
    const { generateProfile } = await import("./data-profile.js");
    const rows = [{ val: "hello" }, { val: "42" }];
    const profile = generateProfile(rows);
    const valField = profile.fields.find((f) => f.name === "val");
    expect(valField.types).toContain("string");
  });
});

// ─── HTML Structure ───

describe("profile panel HTML structure", () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <div id="profile-panel" class="hidden"></div>
    `;
  });

  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("has the profile panel container", () => {
    const panel = document.getElementById("profile-panel");
    expect(panel).toBeDefined();
    expect(panel.classList.contains("hidden")).toBe(true);
  });

  it("renders profile summary when profile exists", async () => {
    const { generateProfile, renderProfilePanel } = await import("./data-profile.js");
    generateProfile([{ name: "A" }, { name: "B" }]);
    renderProfilePanel();
    const panel = document.getElementById("profile-panel");
    expect(panel.classList.contains("hidden")).toBe(false);
    expect(panel.textContent).toContain("Data Profile");
    expect(panel.textContent).toContain("2 rows");
  });

  it("shows KPI metrics", async () => {
    const { generateProfile, renderProfilePanel } = await import("./data-profile.js");
    generateProfile([{ name: "A" }, { name: "B" }]);
    renderProfilePanel();
    const kpis = document.querySelectorAll(".profile-kpi-val");
    expect(kpis.length).toBeGreaterThanOrEqual(2);
    expect(kpis[0].textContent).toContain("2"); // total rows
  });

  it("shows field rows with fill rate bars", async () => {
    const { generateProfile, renderProfilePanel } = await import("./data-profile.js");
    generateProfile([
      { name: "A", email: "a@a.com" },
      { name: "B", email: "" },
    ]);
    renderProfilePanel();
    const fieldRows = document.querySelectorAll(".profile-field-row");
    expect(fieldRows.length).toBe(2);
  });

  it("shows close button", async () => {
    const { generateProfile, renderProfilePanel } = await import("./data-profile.js");
    generateProfile([{ name: "A" }]);
    renderProfilePanel();
    expect(document.querySelector('[data-action="hide-profile-panel"]')).toBeDefined();
  });

  it("shows empty label for all-empty fields", async () => {
    const { generateProfile, renderProfilePanel } = await import("./data-profile.js");
    generateProfile([{ name: "A", notes: "" }]);
    renderProfilePanel();
    const emptyLabels = document.querySelectorAll(".profile-empty-label");
    expect(emptyLabels.length).toBe(1);
    expect(emptyLabels[0].textContent).toContain("empty");
  });
});

// ─── State Management ───

describe("state management", () => {
  it("getProfileState returns current state", async () => {
    const { generateProfile, getProfileState } = await import("./data-profile.js");
    const result = generateProfile([{ name: "A" }]);
    expect(getProfileState()).toBe(result);
  });

  it("clearProfileState resets state", async () => {
    const { generateProfile, clearProfileState, getProfileState } = await import("./data-profile.js");
    generateProfile([{ name: "A" }]);
    expect(getProfileState()).not.toBeNull();
    clearProfileState();
    expect(getProfileState()).toBeNull();
  });
});
