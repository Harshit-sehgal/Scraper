/* ═══════════════════════════════════════════
   DataForge — Predictions Smoke Tests
   ═══════════════════════════════════════════ */

import { describe, it, expect, beforeEach, afterEach } from "vitest";

import { renderPredictions } from "./predictions.js";

beforeEach(() => {
  document.body.innerHTML = `
    <div id="dash-predictions"></div>
    <div id="dash-systemic-risk" class="dash-badge"></div>
  `;
});

afterEach(() => {
  document.body.innerHTML = "";
});

describe("predictions module", () => {
  it("exports renderPredictions as a function", () => {
    expect(typeof renderPredictions).toBe("function");
  });

  it("renders stable empty state when no predictions exist", () => {
    renderPredictions({ predictions: [], systemic_risk_level: "low" });
    const el = document.getElementById("dash-predictions");
    expect(el?.innerHTML).toContain("stable");
  });

  it("renders prediction cards when data is provided", () => {
    renderPredictions({
      predictions: [
        {
          domain: "example.com",
          risk_level: "high",
          predicted_failure_type: "timeout",
          confidence: 0.85,
          health_score_current: 45,
          estimated_time_to_failure_hours: 2.5,
          evidence: ["Latency spike"],
          recommended_actions: ["Scale up"],
        },
      ],
      systemic_risk_level: "medium",
    });
    const el = document.getElementById("dash-predictions");
    expect(el?.innerHTML).toContain("example.com");
    expect(el?.innerHTML).toContain("HIGH");
    expect(el?.innerHTML).toContain("85%");
  });
});
