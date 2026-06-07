/**
 * Telemetry — renders the recent telemetry stats panel in the operations dashboard.
 *
 * Exposes a single exported function ``renderTelemetry(data)`` that
 * updates the ``#dash-telemetry`` DOM element with data from the
 * dashboard API's ``telemetry`` field.
 *
 * The function is self-contained so it can be imported by ``dashboard.js``
 * or other views without creating circular dependencies.
 */

/**
 * Render telemetry data into the operations dashboard DOM.
 *
 * @param {object} data Telemetry response object
 * @param {number} [data.recent_scrapes] - Total recent scrape attempts
 * @param {number} [data.recent_successes] - Successful scrapes
 * @param {number} [data.recent_failures] - Failed scrapes
 * @param {number} [data.success_rate] - Success rate (0-1)
 */
export function renderTelemetry(data) {
  if (!data || typeof data !== "object") return;

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
