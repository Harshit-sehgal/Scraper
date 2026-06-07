/* ═══════════════════════════════════════════
   DataForge — Domain Health Rendering
   ═══════════════════════════════════════════ */

/**
 * Render domain health metrics into the #dash-domains container.
 *
 * Renders a 6-card metrics grid (monitored, healthy, degrading,
 * unhealthy, critical, health rate %) plus a stacked health bar.
 *
 * Shows an empty state when no domains are monitored.
 *
 * @param {object} data - Dashboard data object with a ``domains``
 *        sub-object containing ``total_monitored``, ``healthy``,
 *        ``degrading``, ``unhealthy``, and ``critical`` counts.
 */
export function renderDomainHealth(data) {
  if (!data) return;
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
