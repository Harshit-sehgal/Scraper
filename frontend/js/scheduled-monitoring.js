/* ═══════════════════════════════════════════
   DataForge — Scheduled Monitoring Dashboard
   ═══════════════════════════════════════════
   Lists scheduled jobs, shows change detection
   results, and allows enabling/disabling jobs. */

import { API, apiFetch } from "./api.js";
import { attrStr, esc, toast } from "./utils.js";

// ─── State ───
let _scheduledJobs = [];
let _isLoading = false;

const FREQUENCY_LABELS = {
  hourly: "Every hour",
  daily: "Daily",
  weekly: "Weekly",
  monthly: "Monthly",
};

// ─── Data Fetching ───

export async function refreshScheduledJobs() {
  if (_isLoading) return;
  _isLoading = true;

  try {
    const res = await apiFetch(`${API}/api/scheduled?limit=100`);
    if (!res.ok) {
      if (res.status === 401 || res.status === 403) {
        toast("Authentication required to view scheduled jobs.", "warning");
        return;
      }
      throw new Error("Failed to fetch scheduled jobs");
    }
    const data = await res.json();
    _scheduledJobs = Array.isArray(data.items) ? data.items : [];
    _renderJobs(_scheduledJobs);
    _updateKPIs(_scheduledJobs);
  } catch (err) {
    toast(err.message || "Failed to load scheduled jobs", "error");
  } finally {
    _isLoading = false;
  }
}

async function _fetchChangesForJob(jobId) {
  try {
    const res = await apiFetch(`${API}/api/scheduled/${jobId}/changes`);
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

// ─── Rendering ───

function _renderJobs(jobs) {
  const container = document.getElementById("scheduled-list");
  const emptyState = document.getElementById("scheduled-empty-state");
  if (!container) return;

  // Remove existing job rows
  container.querySelectorAll(".scheduled-row").forEach((row) => row.remove());

  if (jobs.length === 0) {
    if (emptyState) emptyState.style.display = "";
    return;
  }

  if (emptyState) emptyState.style.display = "none";

  for (const job of jobs) {
    const row = document.createElement("div");
    row.className = "scheduled-row";
    row.dataset.jobId = job.id;
    row.innerHTML = _buildJobRow(job);
    container.appendChild(row);

    // Fetch change detection data asynchronously
    _fetchChangesForJob(job.id)
      .then((changes) => {
        if (changes) {
          const changesEl = row.querySelector(".scheduled-changes");
          if (changesEl) {
            changesEl.innerHTML = _buildChangesSummary(changes);
          }
        }
      })
      .catch(() => {});
  }
}

function _buildJobRow(job) {
  const isEnabled = job.enabled !== false;
  const freq = FREQUENCY_LABELS[job.frequency] || job.frequency || "—";
  const lastRun = job.last_run_at ? _formatDate(job.last_run_at) : "Never";
  const lastStatus = job.last_run_status || "—";
  const lastRecords = job.last_run_records_count ?? "—";

  const statusClass =
    {
      completed: "badge completed",
      degraded: "badge degraded",
      empty_result: "badge empty_result",
      failed: "badge failed",
      running: "badge running",
    }[lastStatus] || "badge pending";

  return `
    <div class="scheduled-row-main">
      <div class="scheduled-info">
        <div class="scheduled-name">${esc(job.name)}</div>
        <div class="scheduled-meta">
          <span class="scheduled-frequency">${esc(freq)}</span>
          <span class="scheduled-divider">·</span>
          <span>Last: ${esc(lastRun)}</span>
          <span class="scheduled-divider">·</span>
          <span class="${statusClass}">${esc(lastStatus)}</span>
        </div>
      </div>
      <div class="scheduled-stats">
        <div class="scheduled-stat">
          <span class="scheduled-stat-val">${esc(String(lastRecords))}</span>
          <span class="scheduled-stat-label">records</span>
        </div>
      </div>
      <div class="scheduled-actions">
        <label class="scheduled-toggle-label">
          <input type="checkbox" class="scheduled-toggle" data-job-id="${attrStr(job.id)}"
            ${isEnabled ? "checked" : ""}
            aria-label="Toggle ${esc(job.name)}" />
          <span class="scheduled-toggle-track"></span>
        </label>
        <button type="button" class="btn ghost small danger-ghost" data-action="delete-scheduled-job" data-id="${attrStr(job.id)}"
          title="Delete scheduled job" aria-label="Delete scheduled job">
          <span data-icon="trash" aria-hidden="true"></span>
        </button>
      </div>
    </div>
    <div class="scheduled-changes">
      <span class="scheduled-changes-loading">Checking for changes…</span>
    </div>
  `;
}

function _buildChangesSummary(changes) {
  if (!changes) {
    return '<span class="scheduled-changes-none">No change data available</span>';
  }

  const hasChanges = changes.changes_detected;
  const delta = changes.record_count_delta;
  const statusChanged = changes.status_changed;
  const freqMet = changes.frequency_met;

  let parts = [];

  if (hasChanges) {
    if (delta !== 0) {
      const direction = delta > 0 ? "↑" : "↓";
      const className = delta > 0 ? "change-positive" : "change-negative";
      parts.push(
        `<span class="${className}">${direction} ${Math.abs(delta)} record${Math.abs(delta) !== 1 ? "s" : ""}</span>`,
      );
    }
    if (statusChanged) {
      parts.push(
        `<span class="change-warning">⟳ Status: ${esc(changes.previous_status || "—")} → ${esc(changes.last_status)}</span>`,
      );
    }
    parts.push(`<span class="change-detected-badge">Change detected</span>`);
  } else {
    parts.push(`<span class="change-none">No changes</span>`);
  }

  if (freqMet === false) {
    parts.push(`<span class="change-warning">⏰ Frequency gap unusual</span>`);
  }

  const recordsLine =
    changes.last_records_count != null
      ? `<span class="change-meta">Last run: ${changes.last_records_count} records · ${esc(changes.message || "")}</span>`
      : "";

  return `
    <div class="scheduled-changes-summary ${hasChanges ? "has-changes" : "no-changes"}">
      <div class="scheduled-changes-icons">${parts.join(" ")}</div>
      ${recordsLine}
    </div>
  `;
}

function _updateKPIs(jobs) {
  const total = jobs.length;
  const enabled = jobs.filter((j) => j.enabled !== false).length;
  const failed = jobs.filter((j) => j.last_run_status === "failed").length;
  const withChanges = jobs.filter((j) => j.changes_detected).length;

  setEl("scheduled-kpi-total", total);
  setEl("scheduled-kpi-enabled", enabled);
  setEl("scheduled-kpi-failed", failed);
  setEl("scheduled-kpi-changes", withChanges);

  const updatedEl = document.getElementById("scheduled-last-updated");
  if (updatedEl) {
    updatedEl.textContent = "Updated " + new Date().toLocaleTimeString();
  }
}

// ─── Actions ───

export async function toggleScheduledJob(jobId, enabled) {
  try {
    const params = new URLSearchParams({ enabled: String(enabled) });
    const res = await apiFetch(`${API}/api/scheduled/${jobId}?${params.toString()}`, {
      method: "PUT",
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to update scheduled job");
    }
    toast(`Scheduled job ${enabled ? "enabled" : "disabled"}`, "success");
    await refreshScheduledJobs();
  } catch (err) {
    toast(err.message, "error");
  }
}

export async function deleteScheduledJob(jobId) {
  try {
    const res = await apiFetch(`${API}/api/scheduled/${jobId}`, {
      method: "DELETE",
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to delete scheduled job");
    }
    toast("Scheduled job deleted", "success");
    await refreshScheduledJobs();
  } catch (err) {
    toast(err.message, "error");
  }
}

// ─── Init ───

export function initScheduledMonitoring() {
  // Toggle handlers
  document.addEventListener("change", (e) => {
    const toggle = e.target.closest(".scheduled-toggle");
    if (toggle) {
      const jobId = toggle.dataset.jobId;
      if (jobId) toggleScheduledJob(jobId, toggle.checked);
    }
  });

  // Refresh button
  const refreshBtn = document.getElementById("btn-refresh-scheduled");
  if (refreshBtn) {
    refreshBtn.addEventListener("click", refreshScheduledJobs);
  }
}

// ─── Helpers ───

function setEl(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

function _formatDate(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString([], {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}
