/* ═══════════════════════════════════════════
   DataForge — Jobs Management Tests
   ═══════════════════════════════════════════ */

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { applyJobFilters, updateKPIs, getJobsCache, getPollers } from "./jobs.js";

// ─── applyJobFilters ───────────────────────────────────────────────────────

describe("applyJobFilters()", () => {
  const jobs = [
    { id: "1", name: "Chennai Designers", topic: "interior design", status: "completed" },
    { id: "2", name: "Mumbai Restaurants", topic: "food delivery", status: "running" },
    { id: "3", name: "Delhi Hotels", topic: "accommodation", status: "failed" },
    { id: "4", name: "Bangalore Tech", topic: "startups", status: "pending" },
  ];

  beforeEach(() => {
    // Set up the filter DOM elements
    const search = document.createElement("input");
    search.id = "jobs-search";
    search.value = "";
    document.body.appendChild(search);

    const status = document.createElement("select");
    status.id = "jobs-status-filter";
    // Add the same options that exist in the real HTML
    const statuses = ["all", "pending", "discovering", "running", "completed", "canceled", "failed"];
    for (const s of statuses) {
      const opt = document.createElement("option");
      opt.value = s;
      opt.textContent = s;
      status.appendChild(opt);
    }
    status.value = "all";
    document.body.appendChild(status);
  });

  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("returns all jobs when no filters are set", () => {
    const result = applyJobFilters(jobs);
    expect(result).toHaveLength(4);
  });

  it("filters by search query matching name", () => {
    document.getElementById("jobs-search").value = "chennai";
    const result = applyJobFilters(jobs);
    expect(result).toHaveLength(1);
    expect(result[0].id).toBe("1");
  });

  it("filters by search query matching topic", () => {
    document.getElementById("jobs-search").value = "food";
    const result = applyJobFilters(jobs);
    expect(result).toHaveLength(1);
    expect(result[0].id).toBe("2");
  });

  it("is case-insensitive", () => {
    document.getElementById("jobs-search").value = "CHENNAI";
    const result = applyJobFilters(jobs);
    expect(result).toHaveLength(1);
  });

  it("filters by status", () => {
    document.getElementById("jobs-status-filter").value = "failed";
    const result = applyJobFilters(jobs);
    expect(result).toHaveLength(1);
    expect(result[0].id).toBe("3");
  });

  it("combines status and search filters", () => {
    document.getElementById("jobs-search").value = "mumbai";
    document.getElementById("jobs-status-filter").value = "running";
    const result = applyJobFilters(jobs);
    expect(result).toHaveLength(1);
    expect(result[0].id).toBe("2");
  });

  it("returns empty array when no jobs match", () => {
    document.getElementById("jobs-search").value = "nonexistent";
    const result = applyJobFilters(jobs);
    expect(result).toHaveLength(0);
  });

  it("returns all jobs when status is 'all'", () => {
    document.getElementById("jobs-status-filter").value = "all";
    const result = applyJobFilters(jobs);
    expect(result).toHaveLength(4);
  });

  it("handles empty jobs array", () => {
    const result = applyJobFilters([]);
    expect(result).toHaveLength(0);
  });

  it("handles jobs with undefined name or topic", () => {
    const ragged = [
      { id: "5", name: undefined, topic: "unknown", status: "completed" },
      { id: "6", name: "Valid", topic: undefined, status: "running" },
    ];
    const result = applyJobFilters(ragged);
    expect(result).toHaveLength(2);
  });
});

// ─── updateKPIs ────────────────────────────────────────────────────────────

describe("updateKPIs()", () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <span id="kpi-total">0</span>
      <span id="kpi-running">0</span>
      <span id="kpi-done">0</span>
      <span id="kpi-records">0</span>
    `;
  });

  it("updates total count", () => {
    updateKPIs([{ status: "completed" }, { status: "running" }]);
    expect(document.getElementById("kpi-total").textContent).toBe("2");
  });

  it("counts running/discovering/pending as active", () => {
    updateKPIs([{ status: "running" }, { status: "discovering" }, { status: "pending" }, { status: "completed" }]);
    expect(document.getElementById("kpi-running").textContent).toBe("3");
  });

  it("counts terminal statuses as done", () => {
    updateKPIs([
      { status: "completed" },
      { status: "degraded" },
      { status: "empty_result" },
      { status: "canceled" },
      { status: "running" },
    ]);
    expect(document.getElementById("kpi-done").textContent).toBe("4");
  });

  it("sums filtered_records", () => {
    updateKPIs([{ filtered_records: 10 }, { filtered_records: 25 }, { filtered_records: 5 }]);
    expect(document.getElementById("kpi-records").textContent).toBe("40");
  });

  it("handles missing filtered_records as zero", () => {
    updateKPIs([{ status: "completed" }, { status: "running" }]);
    expect(document.getElementById("kpi-records").textContent).toBe("0");
  });

  it("handles empty job list", () => {
    updateKPIs([]);
    expect(document.getElementById("kpi-total").textContent).toBe("0");
    expect(document.getElementById("kpi-running").textContent).toBe("0");
    expect(document.getElementById("kpi-done").textContent).toBe("0");
    expect(document.getElementById("kpi-records").textContent).toBe("0");
  });
});

// ─── State Accessors ────────────────────────────────────────────────────────

describe("state accessors", () => {
  it("getJobsCache returns initial empty array", () => {
    expect(getJobsCache()).toEqual([]);
  });

  it("getPollers returns initial empty object", () => {
    expect(getPollers()).toEqual({});
  });
});
