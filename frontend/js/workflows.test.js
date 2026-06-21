/* ═══════════════════════════════════════════
   DataForge — Workflows Smoke Tests
   ═══════════════════════════════════════════ */

import { describe, it, expect, beforeEach, afterEach } from "vitest";

import { refreshWorkflows, onWorkflowAction } from "./workflows.js";

beforeEach(() => {
  document.body.innerHTML = `
    <div id="workflows-list"></div>
    <div id="workflows-detail-pane"></div>
    <div id="workflows-kpi-total"></div>
    <div id="workflows-kpi-runs"></div>
    <div id="workflows-kpi-ok"></div>
    <div id="workflows-kpi-fail"></div>
  `;
});

afterEach(() => {
  document.body.innerHTML = "";
});

describe("workflows module", () => {
  it("exports refreshWorkflows as a function", () => {
    expect(typeof refreshWorkflows).toBe("function");
  });

  it("exports onWorkflowAction as a function", () => {
    expect(typeof onWorkflowAction).toBe("function");
  });
});
