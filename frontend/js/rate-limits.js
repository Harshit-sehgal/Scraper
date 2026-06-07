/**
 * Rate Limits — renders the rate limit stats panel in the operations dashboard.
 *
 * Exposes a single exported function ``renderRateLimits(data)`` that
 * updates the ``#dash-rate-limits`` and ``#dash-rate-limit-tier`` DOM
 * elements with data from ``GET /api/system/rate-limit-stats``.
 *
 * The function is intentionally self-contained (no imports from the
 * dashboard module) so callers in ``dashboard.js`` or other views can
 * use it without creating circular dependencies.
 */

/**
 * Render the rate-limit-stats response into the operations dashboard DOM.
 *
 * @param {object} data Response from ``GET /api/system/rate-limit-stats``
 * @param {boolean} data.enabled - Whether rate limiting is active
 * @param {number} data.global_limit_per_window - Aggregate tier cap
 * @param {number} data.global_window_seconds - Window for the aggregate tier
 * @param {boolean} data.per_ip_enabled - Whether per-IP tier is active
 * @param {number} data.per_ip_limit_per_window - Per-IP tier cap
 * @param {number} data.per_ip_window_seconds - Window for per-IP tier
 * @param {number} data.active_keys - Distinct client keys currently tracked
 * @param {object} [data.route_limits] - Per-route override limits (optional)
 */
export function renderRateLimits(data) {
  if (!data || typeof data !== "object") return;

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
