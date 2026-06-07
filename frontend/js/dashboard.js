/* ═══════════════════════════════════════════
   DataForge — Operations Dashboard
   ═══════════════════════════════════════════ */

import { esc, attrStr, toast } from "./utils.js";
import { API, apiFetch } from "./api.js";

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

// ─── Governance ───

function renderGovernance(data) {
  const gov = document.getElementById("dash-governance");
  if (!gov) return;

  const resources = data.resources || {};
  const browser = data.browser || {};
  const governor = data.governor || {};

  gov.innerHTML = `
        <div class="dash-metrics-grid">
            <div class="dash-metric">
                <span class="dash-metric-label">Active Mode</span>
                <span class="dash-metric-val">${esc(data.active_mode || "—")}</span>
            </div>
            <div class="dash-metric">
                <span class="dash-metric-label">Active Browsers</span>
                <span class="dash-metric-val">${browser.active_contexts ?? "—"} / ${browser.total_contexts ?? "—"}</span>
            </div>
            <div class="dash-metric">
                <span class="dash-metric-label">Proxy Health</span>
                <span class="dash-metric-val">${resources.proxy_health != null ? `${(resources.proxy_health * 100).toFixed(0)}%` : "—"}</span>
            </div>
            <div class="dash-metric">
                <span class="dash-metric-label">Token Spend</span>
                <span class="dash-metric-val">$${(governor.token_spend_dollars || 0).toFixed(3)}</span>
            </div>
            <div class="dash-metric">
                <span class="dash-metric-label">Queue Sheds</span>
                <span class="dash-metric-val">${governor.queue_sheds ?? 0}</span>
            </div>
            <div class="dash-metric">
                <span class="dash-metric-label">Browser Prunes</span>
                <span class="dash-metric-val">${governor.browser_prunes ?? 0}</span>
            </div>
        </div>
    `;
}

// ─── Domain Health ───

function renderDomainHealth(data) {
  const el = document.getElementById("dash-domains");
  if (!el) return;

  const domains = data.domains || {};
  const total = domains.total_monitored || 0;

  if (!total) {
    el.innerHTML = '<div class="dash-empty">No domains monitored yet</div>';
    return;
  }

  const healthy = domains.healthy || 0;
  const degrading = domains.degrading || 0;
  const unhealthy = domains.unhealthy || 0;
  const critical = domains.critical || 0;
  const pctHealthy = total > 0 ? Math.round((healthy / total) * 100) : 0;

  el.innerHTML = `
        <div class="dash-metrics-grid">
            <div class="dash-metric">
                <span class="dash-metric-label">Monitored</span>
                <span class="dash-metric-val">${total}</span>
            </div>
            <div class="dash-metric">
                <span class="dash-metric-label" style="color:var(--success)">Healthy</span>
                <span class="dash-metric-val" style="color:var(--success)">${healthy}</span>
            </div>
            <div class="dash-metric">
                <span class="dash-metric-label" style="color:var(--warning)">Degrading</span>
                <span class="dash-metric-val" style="color:var(--warning)">${degrading}</span>
            </div>
            <div class="dash-metric">
                <span class="dash-metric-label" style="color:#8a3a10">Unhealthy</span>
                <span class="dash-metric-val" style="color:#8a3a10">${unhealthy}</span>
            </div>
            <div class="dash-metric">
                <span class="dash-metric-label" style="color:var(--danger)">Critical</span>
                <span class="dash-metric-val" style="color:var(--danger)">${critical}</span>
            </div>
            <div class="dash-metric">
                <span class="dash-metric-label">Health Rate</span>
                <span class="dash-metric-val">${pctHealthy}%</span>
            </div>
        </div>
        <div class="dash-health-bar">
            <div class="dash-health-bar-track">
                <div class="dash-health-fill dash-health-healthy" style="width:${total > 0 ? (healthy / total) * 100 : 0}%"></div>
                <div class="dash-health-fill dash-health-degrading" style="width:${total > 0 ? (degrading / total) * 100 : 0}%"></div>
                <div class="dash-health-fill dash-health-bad" style="width:${total > 0 ? ((unhealthy + critical) / total) * 100 : 0}%"></div>
            </div>
        </div>
    `;
}

// ─── Predictions ───

function renderPredictions(data) {
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
    el.innerHTML = '<div class="dash-empty">No degradation predictions — system looks stable</div>';
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
      const confidence = p.confidence != null ? `${(p.confidence * 100).toFixed(0)}%` : "—";
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
                        <div class="dash-prediction-timer">⏱ ~${p.estimated_time_to_failure_hours.toFixed(0)}h to failure</div>
                    `
                        : ""
                    }
                    ${
                      p.evidence?.length
                        ? `
                        <div class="dash-prediction-evidence">${p.evidence.map((e) => `<span>• ${esc(e)}</span>`).join("")}</div>
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

// ─── Rate Limits ───

function renderRateLimits(data) {
  const el = document.getElementById("dash-rate-limits");
  if (!el) return;

  const tierBadge = document.getElementById("dash-rate-limit-tier");
  if (tierBadge && data.backend) {
    tierBadge.textContent = data.backend.toUpperCase();
  }

  const remaining_percent = data.global_limit > 0 ? Math.round((data.global_remaining / data.global_limit) * 100) : 0;
  const barColor =
    remaining_percent > 50 ? "var(--success)" : remaining_percent > 20 ? "var(--warning)" : "var(--danger)";

  el.innerHTML = `
        <div class="dash-metrics-grid">
            <div class="dash-metric">
                <span class="dash-metric-label">Global Limit</span>
                <span class="dash-metric-val">${data.global_limit ?? "—"} / min</span>
            </div>
            <div class="dash-metric">
                <span class="dash-metric-label">Global Remaining</span>
                <span class="dash-metric-val" style="color:${barColor}">${data.global_remaining ?? "—"}</span>
            </div>
            <div class="dash-metric">
                <span class="dash-metric-label">Per-IP Limit</span>
                <span class="dash-metric-val">${data.per_ip_limit ?? "—"} / min</span>
            </div>
            <div class="dash-metric">
                <span class="dash-metric-label">Per-IP Remaining</span>
                <span class="dash-metric-val">${data.per_ip_remaining ?? "—"}</span>
            </div>
            <div class="dash-metric">
                <span class="dash-metric-label">Window</span>
                <span class="dash-metric-val">${data.window_seconds ?? "—"}s</span>
            </div>
            <div class="dash-metric">
                <span class="dash-metric-label">Client IP</span>
                <span class="dash-metric-val" style="font-size:0.75rem;font-family:monospace">${esc(data.client_ip || "—")}</span>
            </div>
        </div>
        <div class="dash-rate-limit-bar" style="margin-top:0.5rem">
            <div style="display:flex;justify-content:space-between;font-size:0.7rem;color:var(--ink-soft);margin-bottom:0.15rem">
                <span>Global capacity</span>
                <span>${data.global_remaining ?? 0} / ${data.global_limit ?? 0}</span>
            </div>
            <div style="height:4px;background:var(--bg-soft);border-radius:2px;overflow:hidden">
                <div style="height:100%;width:${Math.min(remaining_percent, 100)}%;background:${barColor};border-radius:2px;transition:width 0.3s ease"></div>
            </div>
        </div>
    `;
}

// ─── Telemetry ───

function renderTelemetry(data) {
  const el = document.getElementById("dash-telemetry");
  if (!el) return;

  el.innerHTML = `
        <div class="dash-metrics-grid">
            <div class="dash-metric">
                <span class="dash-metric-label">Recent Scrapes</span>
                <span class="dash-metric-val">${data.recent_scrapes ?? 0}</span>
            </div>
            <div class="dash-metric">
                <span class="dash-metric-label" style="color:var(--success)">Successes</span>
                <span class="dash-metric-val" style="color:var(--success)">${data.recent_successes ?? 0}</span>
            </div>
            <div class="dash-metric">
                <span class="dash-metric-label" style="color:var(--danger)">Failures</span>
                <span class="dash-metric-val" style="color:var(--danger)">${data.recent_failures ?? 0}</span>
            </div>
            <div class="dash-metric">
                <span class="dash-metric-label">Success Rate</span>
                <span class="dash-metric-val">${data.success_rate != null ? `${(data.success_rate * 100).toFixed(0)}%` : "—"}</span>
            </div>
        </div>
    `;
}

// ─── Rate Limits ───

function renderRateLimits(data) {
  const badge = document.getElementById("dash-rate-limit-tier");
  if (badge) {
    if (data.enabled) {
      badge.textContent = "ENABLED";
      badge.style.background = "var(--success-soft)";
      badge.style.color = "var(--success)";
    } else {
      badge.textContent = "DISABLED";
      badge.style.background = "var(--danger-soft)";
      badge.style.color = "var(--danger)";
    }
  }

  const el = document.getElementById("dash-rate-limits");
  if (!el) return;

  if (!data.enabled) {
    el.innerHTML = '<div class="dash-empty">Rate limiting is currently disabled</div>';
    return;
  }

  el.innerHTML = `
        <div class="dash-metrics-grid" style="grid-template-columns: repeat(2, 1fr)">
            <div class="dash-metric">
                <span class="dash-metric-label">Global Limit</span>
                <span class="dash-metric-val">${data.global_limit_per_window || 0} req / ${data.global_window_seconds || 0}s</span>
            </div>
            <div class="dash-metric">
                <span class="dash-metric-label">Per-IP Limit</span>
                <span class="dash-metric-val">${data.per_ip_enabled ? `${data.per_ip_limit_per_window} req / ${data.per_ip_window_seconds}s` : "DISABLED"}</span>
            </div>
            <div class="dash-metric" style="grid-column: span 2">
                <span class="dash-metric-label">Active Tracked Clients</span>
                <span class="dash-metric-val">${data.active_keys ?? 0}</span>
            </div>
        </div>
    `;
}

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
