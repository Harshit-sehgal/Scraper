/* ═══════════════════════════════════
   DataForge — System info panel
   ═══════════════════════════════════
 *
 * Renders a compact, sortable info block on the Dashboard view
 * showing live job counts, recycle-bin size, queue depth, and
 * (if present) the worker heartbeats. Backed by
 * ``GET /api/system/status``.
 */

import { apiFetch, getSessionRole } from "./api.js";

const REFRESH_MS = 30_000;

let timer = null;

// ``GET /api/system/status`` requires ADMIN or OPERATOR. Non-admin
// callers get 403, which (via apiFetch) pops the API-key modal every
// 15s — so skip polling entirely for users whose session role is a
// plain ``user`` (F-015).
function _isAuthorizedViewer() {
  const role = getSessionRole() || "";
  return role === "admin" || role === "operator";
}

function _setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value === undefined || value === null ? "—" : String(value);
}

function _setKpis(status) {
  // F-002: the backend ``GET /api/system/status`` returns the job counts
  // under ``status.jobs.{total,active,completed,failed}`` — not the
  // top-level ``status.total_jobs`` / ``status.active`` / ``status.counts``
  // paths this function previously read (which left 4/6 KPIs stuck at
  // "—" via the ``?? "—"`` fallback).
  const jobs = status.jobs || {};
  _setText("sysinfo-jobs-total", jobs.total ?? "—");
  _setText("sysinfo-jobs-active", jobs.active ?? "—");
  _setText("sysinfo-jobs-completed", jobs.completed ?? "—");
  _setText("sysinfo-jobs-failed", jobs.failed ?? "—");
  _setText("sysinfo-recycle", status.recycle_bin_count ?? "—");

  const queue = status.queue || {};
  _setText("sysinfo-queue-pending", queue.pending ?? "—");
  _setText("sysinfo-queue-running", queue.running ?? "—");
  _setText("sysinfo-queue-dead-letter", queue.dead_letter ?? "—");
  _setText("sysinfo-queue-max", queue.max_concurrency ?? "—");

  _setText("sysinfo-backend", status.backend || status.storage_backend || "sqlite");
  const refreshedAt = new Date().toLocaleTimeString();
  _setText("sysinfo-refreshed-at", refreshedAt);
}

function _renderWorkers(workers) {
  const container = document.getElementById("sysinfo-workers");
  if (!container) return;
  container.innerHTML = "";
  if (!workers || workers.length === 0) {
    container.innerHTML = '<p class="subtle">No workers registered.</p>';
    return;
  }
  const tbl = document.createElement("table");
  tbl.className = "table sysinfo-table";
  tbl.innerHTML = `
    <thead>
      <tr>
        <th>Worker ID</th>
        <th>Hostname</th>
        <th>PID</th>
        <th>Last heartbeat</th>
        <th>Status</th>
      </tr>
    </thead>
    <tbody></tbody>
  `;
  const tbody = tbl.querySelector("tbody");
  for (const w of workers) {
    const tr = document.createElement("tr");
    const lastHb = w.last_heartbeat ? new Date(w.last_heartbeat).toLocaleString() : "—";
    tr.appendChild(td(w.worker_id || "—"));
    tr.appendChild(td(w.hostname || "—"));
    tr.appendChild(td(w.pid || "—"));
    tr.appendChild(td(lastHb));

    const statusCell = document.createElement("td");
    const statusBadge = document.createElement("span");
    statusBadge.className = w.is_stale ? "badge canceled" : "badge completed";
    statusBadge.textContent = w.is_stale ? "stale" : "active";
    statusCell.appendChild(statusBadge);
    tr.appendChild(statusCell);

    tbody.appendChild(tr);
  }
  container.appendChild(tbl);
}

function td(text) {
  const td = document.createElement("td");
  td.textContent = text;
  return td;
}

function _setError(message) {
  const container = document.getElementById("sysinfo-error");
  if (!container) return;
  container.textContent = message || "";
  container.style.display = message ? "block" : "none";
}

export async function refreshSystemInfo() {
  try {
    const resp = await apiFetch("/api/system/status");
    if (!resp.ok) {
      _setError(`Failed to load system status: HTTP ${resp.status}`);
      return;
    }
    _setError("");
    const status = await resp.json();
    _setKpis(status);
    _renderWorkers(status.workers);
  } catch (err) {
    _setError(`Failed to load system status: ${err.message || err}`);
  }
}

export function startSystemInfo() {
  if (timer) return;
  if (!_isAuthorizedViewer()) {
    _setError("System status is admin/operator-only.");
    return;
  }
  void refreshSystemInfo();
  timer = setInterval(() => {
    void refreshSystemInfo();
  }, REFRESH_MS);
}

export function stopSystemInfo() {
  if (timer) {
    clearInterval(timer);
    timer = null;
  }
}
