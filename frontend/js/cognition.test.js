/* ═══════════════════════════════════════════
   DataForge — Cognition State Tests
   ═══════════════════════════════════════════ */

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import {
  renderCommunities,
  renderSchemaPatterns,
  renderExclusions,
  renderRoleSimilarities,
  renderBasins,
  renderCognitionSkeleton,
} from "./cognition.js";

// ─── Setup / Teardown ──────────────────────────────────────────────────────

beforeEach(() => {
  document.body.innerHTML = `
    <span id="kpi-pressure"></span>
    <span id="kpi-integrity"></span>
    <span id="kpi-energy"></span>
    <span id="kpi-exclusions"></span>
    <span id="kpi-basins"></span>
    <div id="community-list"></div>
    <div id="schema-pattern-list"></div>
    <div id="exclusion-list"></div>
    <div id="role-similarity-list"></div>
    <div id="basin-list"></div>
  `;
});

afterEach(() => {
  document.body.innerHTML = "";
});

// ─── renderCognitionSkeleton ───────────────────────────────────────────────

describe("renderCognitionSkeleton()", () => {
  it("replaces KPI values with skeleton bars", () => {
    renderCognitionSkeleton();
    expect(document.getElementById("kpi-pressure").innerHTML).toContain("skeleton-bar");
    expect(document.getElementById("kpi-integrity").innerHTML).toContain("skeleton-bar");
    expect(document.getElementById("kpi-energy").innerHTML).toContain("skeleton-bar");
    expect(document.getElementById("kpi-exclusions").innerHTML).toContain("skeleton-bar");
    expect(document.getElementById("kpi-basins").innerHTML).toContain("skeleton-bar");
  });

  it("fills list containers with skeleton items", () => {
    renderCognitionSkeleton();
    ["community-list", "schema-pattern-list", "exclusion-list", "role-similarity-list", "basin-list"].forEach((id) => {
      const el = document.getElementById(id);
      expect(el.querySelectorAll(".skeleton-bar").length).toBeGreaterThanOrEqual(4);
    });
  });
});

// ─── renderCommunities ─────────────────────────────────────────────────────

describe("renderCommunities()", () => {
  it("renders community role tags", () => {
    renderCommunities([["role-a", "role-b"], ["role-c"]]);
    const el = document.getElementById("community-list");
    expect(el.innerHTML).toContain("role-a");
    expect(el.innerHTML).toContain("role-b");
    expect(el.innerHTML).toContain("role-c");
  });

  it("shows empty state when no communities", () => {
    renderCommunities([]);
    expect(document.getElementById("community-list").innerHTML).toContain("No stable communities");
  });

  it("shows empty state when communities is null", () => {
    renderCommunities(null);
    expect(document.getElementById("community-list").innerHTML).toContain("No stable communities");
  });

  it("escapes HTML in role names", () => {
    renderCommunities([['<script>alert("xss")</script>']]);
    const el = document.getElementById("community-list");
    expect(el.innerHTML).toContain("&lt;script&gt;");
    expect(el.innerHTML).not.toContain("<script>");
  });
});

// ─── renderSchemaPatterns ──────────────────────────────────────────────────

describe("renderSchemaPatterns()", () => {
  const patterns = [
    { roles: ["field-a", "field-b"], count: 5 },
    { roles: ["field-c"], count: 10 },
    { roles: ["field-d"], count: 3 },
  ];

  it("renders sorted by count descending", () => {
    renderSchemaPatterns(patterns);
    const el = document.getElementById("schema-pattern-list");
    const html = el.innerHTML;
    expect(html.indexOf("field-c")).toBeLessThan(html.indexOf("field-a"));
    expect(html.indexOf("field-a")).toBeLessThan(html.indexOf("field-d"));
  });

  it("shows count for each pattern", () => {
    renderSchemaPatterns(patterns);
    const el = document.getElementById("schema-pattern-list");
    expect(el.innerHTML).toContain("Count: 10");
    expect(el.innerHTML).toContain("Count: 5");
  });

  it("shows empty state when no patterns", () => {
    renderSchemaPatterns([]);
    expect(document.getElementById("schema-pattern-list").innerHTML).toContain("No recurring schemas");
  });
});

// ─── renderExclusions ──────────────────────────────────────────────────────

describe("renderExclusions()", () => {
  const exclusions = [
    { roles: ["role-a", "role-b"], strength: 0.9 },
    { roles: ["role-c", "role-d"], strength: 0.5 },
  ];

  it("renders sorted by strength descending", () => {
    renderExclusions(exclusions);
    const el = document.getElementById("exclusion-list");
    const html = el.innerHTML;
    expect(html.indexOf("role-a")).toBeLessThan(html.indexOf("role-c"));
  });

  it("renders strength values", () => {
    renderExclusions(exclusions);
    const el = document.getElementById("exclusion-list");
    expect(el.innerHTML).toContain("0.900");
    expect(el.innerHTML).toContain("0.500");
  });

  it("shows empty state when no exclusions", () => {
    renderExclusions([]);
    expect(document.getElementById("exclusion-list").innerHTML).toContain("No exclusions learned");
  });
});

// ─── renderRoleSimilarities ────────────────────────────────────────────────

describe("renderRoleSimilarities()", () => {
  const compats = [
    { role: "alpha", type: "standard", score: 0.95 },
    { role: "beta", type: "custom", score: 0.72 },
    { role: "gamma", type: "standard", score: 0.3 },
  ];

  it("filters to scores > 0.7", () => {
    renderRoleSimilarities(compats);
    const el = document.getElementById("role-similarity-list");
    expect(el.innerHTML).toContain("alpha");
    expect(el.innerHTML).toContain("beta");
    expect(el.innerHTML).not.toContain("gamma");
  });

  it("renders score values", () => {
    renderRoleSimilarities(compats);
    const el = document.getElementById("role-similarity-list");
    expect(el.innerHTML).toContain("0.950");
    expect(el.innerHTML).toContain("0.720");
  });

  it("shows empty state when no compatibilities", () => {
    renderRoleSimilarities([]);
    expect(document.getElementById("role-similarity-list").innerHTML).toContain("Manifold is cold");
  });

  it("shows empty state when all scores are below threshold", () => {
    renderRoleSimilarities([{ role: "low", type: "a", score: 0.5 }]);
    expect(document.getElementById("role-similarity-list").innerHTML).toContain("Manifold is cold");
  });
});

// ─── renderBasins ──────────────────────────────────────────────────────────

describe("renderBasins()", () => {
  const basins = [
    { token: "email", competing_roles: ["contact", "business"], instability: 0.8, local_energy: 0.5 },
    { token: "phone", competing_roles: ["mobile", "landline"], instability: 0.95, local_energy: 0.3 },
  ];

  it("renders sorted by instability descending", () => {
    renderBasins(basins);
    const el = document.getElementById("basin-list");
    const html = el.innerHTML;
    expect(html.indexOf("phone")).toBeLessThan(html.indexOf("email"));
  });

  it("renders token, competing roles, instability, energy", () => {
    renderBasins(basins);
    const el = document.getElementById("basin-list");
    expect(el.innerHTML).toContain("email");
    expect(el.innerHTML).toContain("contact, business");
    expect(el.innerHTML).toContain("0.800");
    expect(el.innerHTML).toContain("0.500");
  });

  it("shows empty state when no basins", () => {
    renderBasins([]);
    expect(document.getElementById("basin-list").innerHTML).toContain("No active conflict basins");
  });
});
