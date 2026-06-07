/* ═══════════════════════════════════════════
   DataForge — Predictions Rendering Tests
   ═══════════════════════════════════════════ */

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { renderPredictions } from "./predictions.js";

/**
 * Set up the DOM elements that renderPredictions targets.
 */
function setupDOM() {
  const container = document.createElement("div");
  container.id = "dash-predictions";
  container.innerHTML = '<div class="dash-loading">Loading...</div>';

  const badge = document.createElement("span");
  badge.id = "dash-systemic-risk";
  badge.textContent = "—";
  badge.className = "dash-badge";

  document.body.appendChild(container);
  document.body.appendChild(badge);
}

beforeEach(() => {
  document.body.innerHTML = "";
  setupDOM();
});

afterEach(() => {
  document.body.innerHTML = "";
});

const PREDICTION_DATA = {
  systemic_risk_level: "medium",
  predictions: [
    {
      domain: "example.com",
      risk_level: "high",
      predicted_failure_type: "rate_limited",
      confidence: 0.87,
      health_score_current: 42,
      estimated_time_to_failure_hours: 3.5,
      evidence: ["Error rate increased 5x", "Response time >5s"],
      recommended_actions: ["Rotate proxies", "Reduce concurrency"],
    },
  ],
};

// ─── Basic Rendering ───

describe("renderPredictions", () => {
  it("renders systemic risk badge", () => {
    renderPredictions(PREDICTION_DATA);
    const badge = document.getElementById("dash-systemic-risk");
    expect(badge.textContent).toBe("Systemic: MEDIUM");
    expect(badge.className).toContain("risk-medium");
  });

  it("renders domain name", () => {
    renderPredictions(PREDICTION_DATA);
    const el = document.getElementById("dash-predictions");
    expect(el.innerHTML).toContain("example.com");
  });

  it("renders risk level in uppercase", () => {
    renderPredictions(PREDICTION_DATA);
    const el = document.getElementById("dash-predictions");
    expect(el.innerHTML).toContain("HIGH");
  });

  it("renders predicted failure type", () => {
    renderPredictions(PREDICTION_DATA);
    const el = document.getElementById("dash-predictions");
    expect(el.innerHTML).toContain("rate_limited");
  });

  it("renders confidence percentage", () => {
    renderPredictions(PREDICTION_DATA);
    const el = document.getElementById("dash-predictions");
    expect(el.innerHTML).toContain("87%");
  });

  it("renders health score", () => {
    renderPredictions(PREDICTION_DATA);
    const el = document.getElementById("dash-predictions");
    expect(el.innerHTML).toContain("42/100");
  });

  it("renders time to failure", () => {
    renderPredictions(PREDICTION_DATA);
    const el = document.getElementById("dash-predictions");
    expect(el.innerHTML).toContain("4h to failure");
  });

  it("renders evidence items", () => {
    renderPredictions(PREDICTION_DATA);
    const el = document.getElementById("dash-predictions");
    expect(el.textContent).toContain("Error rate increased 5x");
    expect(el.textContent).toContain("Response time >5s");
  });

  it("renders recommended action buttons", () => {
    renderPredictions(PREDICTION_DATA);
    const el = document.getElementById("dash-predictions");
    expect(el.innerHTML).toContain("Rotate proxies");
    expect(el.innerHTML).toContain("Reduce concurrency");
  });

  it("is structured as a prediction card", () => {
    renderPredictions(PREDICTION_DATA);
    const el = document.getElementById("dash-predictions");
    const cards = el.querySelectorAll(".dash-prediction");
    expect(cards.length).toBe(1);
  });

  // ─── Empty / Stable State ───

  it("shows stable message when no predictions", () => {
    renderPredictions({ systemic_risk_level: "low", predictions: [] });
    const el = document.getElementById("dash-predictions");
    expect(el.innerHTML).toContain("system looks stable");
  });

  it("shows stable message when predictions key is missing", () => {
    renderPredictions({});
    const el = document.getElementById("dash-predictions");
    expect(el.innerHTML).toContain("system looks stable");
  });

  it("defaults systemic risk to low when missing", () => {
    renderPredictions({ predictions: [] });
    const badge = document.getElementById("dash-systemic-risk");
    expect(badge.textContent).toBe("Systemic: LOW");
    expect(badge.className).toContain("risk-low");
  });

  // ─── Conditional Rendering ───

  it("does not render timer when hours are missing", () => {
    const data = {
      systemic_risk_level: "low",
      predictions: [{ ...PREDICTION_DATA.predictions[0], estimated_time_to_failure_hours: null }],
    };
    renderPredictions(data);
    const el = document.getElementById("dash-predictions");
    expect(el.innerHTML).not.toContain("h to failure");
  });

  it("does not render evidence when evidence is missing", () => {
    const data = {
      systemic_risk_level: "low",
      predictions: [{ ...PREDICTION_DATA.predictions[0], evidence: null }],
    };
    renderPredictions(data);
    const el = document.getElementById("dash-predictions");
    expect(el.innerHTML).not.toContain("dash-prediction-evidence");
  });

  it("does not render actions when actions are missing", () => {
    const data = {
      systemic_risk_level: "low",
      predictions: [{ ...PREDICTION_DATA.predictions[0], recommended_actions: null }],
    };
    renderPredictions(data);
    const el = document.getElementById("dash-predictions");
    expect(el.innerHTML).not.toContain("dash-prediction-actions");
  });

  it("shows em dash for missing confidence", () => {
    const data = {
      systemic_risk_level: "low",
      predictions: [{ ...PREDICTION_DATA.predictions[0], confidence: null }],
    };
    renderPredictions(data);
    const el = document.getElementById("dash-predictions");
    expect(el.innerHTML).toContain("\u2014");
  });

  it("shows question mark for missing health score", () => {
    const data = {
      systemic_risk_level: "low",
      predictions: [{ ...PREDICTION_DATA.predictions[0], health_score_current: null }],
    };
    renderPredictions(data);
    const el = document.getElementById("dash-predictions");
    expect(el.innerHTML).toContain("?/100");
  });

  // ─── Edge Cases ───

  it("does not crash when container is missing", () => {
    document.body.innerHTML = "";
    expect(() => renderPredictions(PREDICTION_DATA)).not.toThrow();
  });

  it("does not crash on null data", () => {
    expect(() => renderPredictions(null)).not.toThrow();
  });

  it("does not crash on undefined data", () => {
    expect(() => renderPredictions(undefined)).not.toThrow();
  });

  it("does not crash when risk badge is missing", () => {
    const badge = document.getElementById("dash-systemic-risk");
    if (badge) badge.remove();
    expect(() => renderPredictions(PREDICTION_DATA)).not.toThrow();
  });
});
