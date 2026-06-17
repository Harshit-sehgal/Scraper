/* ═══════════════════════════════════
   DataForge — System info panel
   ═══════════════════════════════════
 *
 * Renders a compact, sortable info block on the Dashboard view
 * showing live job counts, recycle-bin size, queue depth, and
 * (if present) the worker heartbeats. Backed by
 * ``GET /api/system/status``.
 */

import { apiFetch } from "./api.js";

const REFRESH_MS = 30_000;

let timer = null;

function _setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value === undefined || value === null ? "—" : String(value);
}

function _setKpis(status) {
  const counts = status.counts || {};
  _setText("sysinfo-jobs-total", status.total_jobs ?? "—");
  _setText("sysinfo-jobs-active", status.active ?? "—");
  _setText("sysinfo-jobs-completed", counts.completed ?? "—");
  _setText("sysinfo-jobs-failed", counts.failed ?? "—");
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
  tbl.className = "sysinfo-table";
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
    const status = w.is_stale ? "Stale" : "Active";
    tr.appendChild(td(w.worker_id || "—"));
    tr.appendChild(td(w.hostname || "—"));
    tr.appendChild(td(w.pid || "—"));
    tr.appendChild(td(lastHb));
    tr.appendChild(td(status));
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
