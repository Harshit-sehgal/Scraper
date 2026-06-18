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
  container.innerHTML = "";
  if (!events || events.length === 0) {
    container.innerHTML = '<p class="subtle">No recent activity.</p>';
    return;
  }
  const ol = document.createElement("ol");
  ol.className = "activity-list";
  for (const ev of events) {
    const li = document.createElement("li");
    li.className = "activity-item";

    const time = document.createElement("span");
    time.className = "activity-time";
    const ts = ev.timestamp || ev.ts;
    time.textContent = ts ? new Date(ts).toLocaleString() : "—";
    li.appendChild(time);

    const cat = document.createElement("span");
    cat.className = `activity-cat activity-cat-${String(ev.category || "system").toLowerCase()}`;
    cat.textContent = String(ev.category || "—");
    li.appendChild(cat);

    const action = document.createElement("span");
    action.className = "activity-action";
    const detail = ev.detail || ev.message || (ev.payload ? JSON.stringify(ev.payload) : ev.action) || "";
    const subject = ev.subject || ev.user_id || ev.actor || "—";
    action.textContent = `${subject} ${detail}`.trim();
    li.appendChild(action);

    if (ev.outcome) {
      const outcome = document.createElement("span");
      outcome.className = `activity-outcome activity-outcome-${String(ev.outcome).toLowerCase()}`;
      outcome.textContent = String(ev.outcome);
      li.appendChild(outcome);
    }

    ol.appendChild(li);
  }
  container.appendChild(ol);
}

function _renderPermissionDenied() {
  const container = document.getElementById("recent-activity-list");
  if (!container) return;
  container.innerHTML = '<p class="subtle">Audit log is admin-only.</p>';
}

function _renderError(message) {
  const container = document.getElementById("recent-activity-list");
  if (!container) return;
  container.innerHTML = `<p class="subtle">${message}</p>`;
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
