/* ═══════════════════════════════════════════
   DataForge — Governance Rendering
   ═══════════════════════════════════════════ */

import { esc } from "./utils.js";

/**
 * Render governance/resource metrics into the #dash-governance container.
 *
 * Renders a 6-card metrics grid: active mode, active/total browsers,
 * proxy health %, token spend, queue sheds, and browser prunes.
 *
 * @param {object} data - Dashboard data object with ``resources``,
 *        ``browser``, and ``governor`` sub-objects.
 */
export function renderGovernance(data) {
  if (!data) return;
  const gov = document.getElementById("dash-governance");
  if (!gov) return;

  const resources = data.resources || {};
  const browser = data.browser || {};
  const governor = data.governor || {};

  gov.innerHTML = `
        <div class="dash-metrics-grid">
            <div class="dash-metric">
                <span class="dash-metric-label">Active Mode</span>
                <span class="dash-metric-val">${esc(data.active_mode || "\u2014")}</span>
            </div>
            <div class="dash-metric">
                <span class="dash-metric-label">Active Browsers</span>
                <span class="dash-metric-val">${browser.active_contexts != null ? Number(browser.active_contexts) : "\u2014"} / ${browser.total_contexts != null ? Number(browser.total_contexts) : "\u2014"}</span>
            </div>
            <div class="dash-metric">
                <span class="dash-metric-label">Proxy Health</span>
                <span class="dash-metric-val">${resources.proxy_health != null ? `${(Number(resources.proxy_health) * 100).toFixed(0)}%` : "\u2014"}</span>
            </div>
            <div class="dash-metric">
                <span class="dash-metric-label">Token Spend</span>
                <span class="dash-metric-val">$${(Number(governor.token_spend_dollars) || 0).toFixed(3)}</span>
            </div>
            <div class="dash-metric">
                <span class="dash-metric-label">Queue Sheds</span>
                <span class="dash-metric-val">${Number(governor.queue_sheds) || 0}</span>
            </div>
            <div class="dash-metric">
                <span class="dash-metric-label">Browser Prunes</span>
                <span class="dash-metric-val">${Number(governor.browser_prunes) || 0}</span>
            </div>
        </div>
    `;
}
