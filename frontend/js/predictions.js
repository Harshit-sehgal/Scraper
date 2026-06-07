/* ═══════════════════════════════════════════
   DataForge — Predictions Rendering
   ═══════════════════════════════════════════ */

import { esc, attrStr } from "./utils.js";

/**
 * Render degradation predictions into the #dash-predictions container.
 *
 * Renders a systemic risk badge and a list of prediction cards. Each
 * card shows the domain, risk level (color-coded), predicted failure
 * type, confidence %, current health score, estimated time to failure,
 * evidence items, and recommended action buttons.
 *
 * Shows a "stable" empty state when no predictions exist.
 *
 * @param {object} data - Predictions data with ``predictions`` array
 *        and ``systemic_risk_level`` string.
 */
export function renderPredictions(data) {
  if (!data) return;
  const el = document.getElementById("dash-predictions");
  if (!el) return;

  const predictions = data.predictions || [];
  const systemic = data.systemic_risk_level || "low";

  const riskBadge = document.getElementById("dash-systemic-risk");
  if (riskBadge) {
    riskBadge.textContent = `Systemic: ${systemic.toUpperCase()}`;
    riskBadge.className = `dash-badge risk-${systemic}`;
  }

  if (!predictions.length) {
    el.innerHTML = '<div class="dash-empty">No degradation predictions \u2014 system looks stable</div>';
    return;
  }

  el.innerHTML = predictions
    .map((p) => {
      const riskColors = {
        critical: "var(--danger)",
        high: "#c7851b",
        medium: "#8a5a10",
        low: "var(--success)",
      };
      const color = riskColors[p.risk_level] || "var(--ink-soft)";
      const confidence = p.confidence != null ? `${(p.confidence * 100).toFixed(0)}%` : "\u2014";
      return `
            <div class="dash-prediction">
                <div class="dash-prediction-header">
                    <span class="dash-prediction-domain">${esc(p.domain)}</span>
                    <span class="dash-prediction-risk" style="color:${color}; background:${color}18;">
                        ${esc(String(p.risk_level || "").toUpperCase())}
                    </span>
                </div>
                <div class="dash-prediction-body">
                    <div class="dash-prediction-detail">
                        <span>Failure: <strong>${esc(p.predicted_failure_type)}</strong></span>
                        <span>Confidence: <strong>${confidence}</strong></span>
                        <span>Health: <strong>${p.health_score_current?.toFixed(0) || "?"}/100</strong></span>
                    </div>
                    ${
                      p.estimated_time_to_failure_hours
                        ? `
                        <div class="dash-prediction-timer">\u23F1 ~${p.estimated_time_to_failure_hours.toFixed(0)}h to failure</div>
                    `
                        : ""
                    }
                    ${
                      p.evidence?.length
                        ? `
                        <div class="dash-prediction-evidence">${p.evidence.map((e) => `<span>\u2022 ${esc(e)}</span>`).join("")}</div>
                    `
                        : ""
                    }
                    ${
                      p.recommended_actions?.length
                        ? `
                        <div class="dash-prediction-actions">
                            ${p.recommended_actions.map((a) => `<button class="btn ghost small" data-action="toast-info" data-message="${attrStr(a)}">${esc(a)}</button>`).join("")}
                        </div>
                    `
                        : ""
                    }
                </div>
            </div>
        `;
    })
    .join("");
}
