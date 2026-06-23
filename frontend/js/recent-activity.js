/* ═══════════════════════════════════
   DataForge — Recent activity panel
   ═══════════════════════════════════
 *
 * Renders the most recent audit events on the Dashboard view.
 * Backed by ``GET /api/system/audit-log``. The endpoint is admin-only
 * so this panel silently renders a friendly notice for non-admin
 * callers rather than erroring out.
 */

import { apiFetch, getSessionRole } from "./api.js";
import { esc } from "./utils.js";

const REFRESH_MS = 60_000;
const MAX_EVENTS = 12;

// ``GET /api/system/audit-log`` is admin-only. Non-admin callers get
// 403, which (via apiFetch) pops the API-key modal every 15s — so skip
// polling for non-admin users (F-015).
function _isAdminViewer() {
  return (getSessionRole() || "") === "admin";
}

let timer = null;

function _setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value === undefined || value === null ? "—" : String(value);
}

function _render(events) {
  const container = document.getElementById("recent-activity-list");
  if (!container) return;
  if (!events || events.length === 0) {
    container.innerHTML = '<p class="subtle">No recent activity.</p>';
    return;
  }

  let html = `
    <table class="table-dash-activity">
      <thead>
        <tr>
          <th>Job ID</th>
          <th>Target</th>
          <th>Status</th>
          <th class="text-right">Timestamp</th>
        </tr>
      </thead>
      <tbody>`;

  for (const ev of events) {
    const ts = ev.timestamp || ev.ts;
    const tsStr = ts ? new Date(ts).toLocaleTimeString() : "—";
    const subject = ev.subject || ev.user_id || ev.actor || "—";
    const detail = ev.detail || ev.message || (ev.payload ? JSON.stringify(ev.payload) : ev.action) || "—";
    const outcome = ev.outcome || "—";

    // Map outcome to badge class
    const badgeClass =
      outcome === "success" || outcome === "ok"
        ? "badge completed"
        : outcome === "failed" || outcome === "error"
          ? "badge failed"
          : "badge pending";
    const badgeLabel =
      outcome === "success" || outcome === "ok"
        ? "Success"
        : outcome === "failed" || outcome === "error"
          ? "Failed"
          : outcome.charAt(0).toUpperCase() + outcome.slice(1);
    const rowClass = outcome === "failed" || outcome === "error" ? "row-failed" : "";

    html += `
        <tr class="${rowClass}">
          <td class="td-activity-id">${esc(String(subject).slice(0, 10))}</td>
          <td class="td-activity-target">${esc(String(detail).slice(0, 60))}</td>
          <td><span class="${badgeClass}">${esc(badgeLabel)}</span></td>
          <td class="td-activity-ts">${esc(tsStr)}</td>
        </tr>`;
  }

  html += `
      </tbody>
    </table>`;

  container.innerHTML = html;
}

function _renderPermissionDenied() {
  const container = document.getElementById("recent-activity-list");
  if (!container) return;
  container.innerHTML = '<p class="subtle">Audit log is admin-only.</p>';
}

function _renderError(message) {
  const container = document.getElementById("recent-activity-list");
  if (!container) return;
  container.innerHTML = `<p class="subtle">${esc(message)}</p>`;
}

function _renderLastRefreshed() {
  _setText("recent-activity-refreshed-at", new Date().toLocaleTimeString());
}

export async function refreshRecentActivity() {
  try {
    const resp = await apiFetch(`/api/system/audit-log?limit=${MAX_EVENTS}`);
    if (resp.status === 403) {
      _renderPermissionDenied();
      _renderLastRefreshed();
      return;
    }
    if (!resp.ok) {
      _renderError(`Failed to load recent activity: HTTP ${resp.status}`);
      _renderLastRefreshed();
      return;
    }
    const body = await resp.json();
    _render(body.items || []);
    _renderLastRefreshed();
  } catch (err) {
    _renderError(`Failed to load recent activity: ${err.message || err}`);
    _renderLastRefreshed();
  }
}

export function startRecentActivity() {
  if (timer) return;
  if (!_isAdminViewer()) {
    _renderError("Audit log is admin-only.");
    _renderLastRefreshed();
    return;
  }
  void refreshRecentActivity();
  timer = setInterval(() => {
    void refreshRecentActivity();
  }, REFRESH_MS);
}

export function stopRecentActivity() {
  if (timer) {
    clearInterval(timer);
    timer = null;
  }
}
