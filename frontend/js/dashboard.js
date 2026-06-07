/* ═══════════════════════════════════════════
   DataForge — Operations Dashboard
   ═══════════════════════════════════════════ */

import { toast } from "./utils.js";
import { API, apiFetch } from "./api.js";
import { renderRateLimits } from "./rate-limits.js";
import { renderTelemetry } from "./telemetry.js";
import { renderGovernance } from "./governance.js";
import { renderDomainHealth } from "./domain-health.js";
import { renderPredictions } from "./predictions.js";

// ─── Refresh Dashboard ───

export async function refreshDashboard() {
  const btn = document.querySelector("#view-dashboard .btn.primary.small");
  if (btn) btn.disabled = true;

  try {
    const [modeRes, dashRes, healthRes, predRes, rateLimitRes] = await Promise.all([
      apiFetch(`${API}/api/operator/mode`).catch(() => null),
      apiFetch(`${API}/api/operator/dashboard`).catch(() => null),
      apiFetch(`${API}/api/operator/health`).catch(() => null),
      apiFetch(`${API}/api/operator/predictions`).catch(() => null),
      apiFetch(`${API}/api/system/rate-limit-stats`).catch(() => null),
    ]);

    const modeData = modeRes?.ok ? await modeRes.json() : null;
    const dashData = dashRes?.ok ? await dashRes.json() : null;
    const healthData = healthRes?.ok ? await healthRes.json() : null;
    const predData = predRes?.ok ? await predRes.json() : null;
    const rateLimitData = rateLimitRes?.ok ? await rateLimitRes.json() : null;

    // Mode switcher
    const modeBadge = document.getElementById("dash-current-mode");
    if (modeBadge && modeData) {
      modeBadge.textContent = modeData.active_mode || "unknown";
      document.querySelectorAll(".mode-btn").forEach((btn) => {
        const isActive = btn.dataset.mode === (modeData.active_mode || "");
        btn.classList.toggle("active", isActive);
      });
    }

    // Health KPIs
    if (healthData) {
      const statusEl = document.getElementById("dash-status-val");
      if (statusEl) {
        statusEl.textContent = healthData.status || "—";
        statusEl.style.color =
          healthData.status === "healthy"
            ? "var(--success)"
            : healthData.status === "degraded"
              ? "var(--warning)"
              : "var(--danger)";
      }
      setEl(
        "dash-success-rate",
        healthData.success_rate != null ? `${(healthData.success_rate * 100).toFixed(0)}%` : "—",
      );
      setEl("dash-active-browsers", String(healthData.active_browsers ?? "—"));
      setEl("dash-domains-degraded", String(healthData.domains_degraded ?? "—"));
    }

    // Governance
    if (dashData) {
      renderGovernance(dashData);
      renderDomainHealth(dashData);
    }

    // Predictions
    if (predData) renderPredictions(predData);

    // Rate Limits
    if (rateLimitData) renderRateLimits(rateLimitData);

    // Telemetry
    if (dashData?.telemetry) renderTelemetry(dashData.telemetry);
  } catch (e) {
    console.error("Dashboard refresh failed:", e);
  } finally {
    if (btn) btn.disabled = false;
  }
}

function setEl(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

// Renderers from external modules:
//   - governance.js       -> renderGovernance
//   - domain-health.js    -> renderDomainHealth
//   - predictions.js      -> renderPredictions
//   - rate-limits.js      -> renderRateLimits
//   - telemetry.js        -> renderTelemetry
// (All imported at the top of this file)

// ─── Switch Operator Mode ───

export async function switchOperatorMode(mode) {
  const feedback = document.getElementById("mode-feedback");
  if (feedback) {
    feedback.textContent = "Switching mode...";
    feedback.className = "mode-feedback";
    feedback.classList.remove("hidden");
  }

  try {
    const res = await apiFetch(`${API}/api/operator/mode`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode }),
      admin: true,
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Mode switch failed");
    }

    const data = await res.json();

    if (feedback) {
      feedback.textContent = `✓ Switched to ${data.active_mode} mode`;
      feedback.className = "mode-feedback mode-feedback-success";
      setTimeout(() => feedback.classList.add("hidden"), 3000);
    }

    toast(`Mode switched to ${data.active_mode}`, "success");
    refreshDashboard();
  } catch (e) {
    if (feedback) {
      feedback.textContent = `✗ ${e.message}`;
      feedback.className = "mode-feedback mode-feedback-error";
      setTimeout(() => feedback.classList.add("hidden"), 5000);
    }
    toast(`Mode switch failed: ${e.message}`, "error");
  }
}
