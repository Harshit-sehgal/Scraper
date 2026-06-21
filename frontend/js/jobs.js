/* ═══════════════════════════════════════════
   DataForge — Jobs Management
   ═══════════════════════════════════════════ */ import {
  esc,
  attrStr,
  toast,
  setEngineStatus,
  setJobsUpdatedAt,
  updateJobsLastUpdatedLabel,
  writeUIState,
  showConfirm,
} from "./utils.js";
import { apiFetch, endpoints } from "./api.js";
import { currentView } from "./views.js";
import { currentJobId, renderLogs, viewResults } from "./results.js";
import { renderFailureBadge, initFailureBadges, attachFailureExplanationToJobRow } from "./failure-explanation.js";

// ─── State ───

let jobsCache = [];
const pollers = {};

// Track the most recently transitioned job ID so renderJobs() can flash it
let _flashJobId = null;

// Track jobs the user just interacted with so the poller's terminal-state
// toast does not double up on the action toast (e.g. clicking "Cancel"
// already shows "Cancellation requested"; the poller must not also show
// "Job canceled" a few seconds later).
const _recentUserActions = new Map(); // jobId -> expiresAt (ms)
const _USER_ACTION_TTL_MS = 8000;

const STATUS_GROUPS = {
  pending: "queued",
  queued: "queued",
  discovering: "running",
  running: "running",
  completed: "completed",
  degraded: "completed",
  empty_result: "completed",
  failed: "failed",
  error: "failed",
  canceled: "cancelled",
  cancelled: "cancelled",
};

const STATUS_LABELS = {
  queued: "Queued",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
};

function _markUserAction(id) {
  _recentUserActions.set(id, Date.now() + _USER_ACTION_TTL_MS);
}

function _consumeRecentUserAction(id) {
  const exp = _recentUserActions.get(id);
  if (exp === undefined) return false;
  _recentUserActions.delete(id);
  return exp >= Date.now();
}

export function getJobsCache() {
  return jobsCache;
}
export function getPollers() {
  return pollers;
}

export function getJobStatusGroup(status) {
  return STATUS_GROUPS[String(status || "").toLowerCase()] || "queued";
}

export function formatJobStatus(status) {
  return STATUS_LABELS[getJobStatusGroup(status)] || "Queued";
}

function formatCreatedAt(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function getIssueCount(job) {
  const warnings = Array.isArray(job.warnings) ? job.warnings.length : 0;
  return warnings + (job.error ? 1 : 0);
}

// ─── Refresh System Status ───

export async function refreshSystemStatus() {
  try {
    const r = await apiFetch(endpoints.systemStatus);
    if (!r.ok) throw new Error("status unavailable");
    const data = await r.json();
    const active = Number((data.jobs || {}).active || 0);
    setEngineStatus(active > 0 ? `Online • ${active} active` : "Online • Idle");
  } catch (_e) {
    setEngineStatus("Offline", true);
  }
}

// ─── Refresh Jobs ───

export async function refreshJobs() {
  // Show skeleton while loading
  renderSkeleton();

  try {
    const res = await apiFetch(endpoints.jobs);
    if (!res.ok) throw new Error("jobs unavailable");
    const data = await res.json();
    jobsCache = Array.isArray(data.jobs) ? data.jobs : [];
    renderJobs(applyJobFilters(jobsCache));
    updateKPIs(jobsCache);
    syncPollers(jobsCache);
    setJobsUpdatedAt(Date.now());
    updateJobsLastUpdatedLabel();
    // Update sidebar activity feed with the latest jobs
    import("./sidebar-activity.js").then((m) => m.updateSidebarActivity(jobsCache)).catch(() => {});
  } catch (_e) {
    setEngineStatus("Offline", true);
    updateJobsLastUpdatedLabel("Unable to refresh");
    // If cache is empty, show empty state on error
    if (!jobsCache.length) {
      const list = document.getElementById("jobs-list");
      const empty = document.getElementById("empty-state");
      if (list && empty) {
        list.innerHTML = "";
        list.appendChild(empty);
        empty.classList.remove("hidden");
        const titleEl = empty.querySelector(".empty-state-title") || empty.querySelector("h3");
        const descEl = empty.querySelector(".empty-state-desc") || empty.querySelector("p");
        if (titleEl) titleEl.textContent = "Could not load jobs";
        if (descEl) descEl.textContent = "Could not load jobs. Check whether the backend is running.";
      }
    }
  }
}

// ─── Skeleton Loading ───

function renderSkeleton() {
  const list = document.getElementById("jobs-list");
  if (!list) return;

  const rows = Array.from(
    { length: 4 },
    () => `
        <div class="skeleton">
            <div class="skeleton-grid">
                <div class="skeleton-bar wide"></div>
                <div class="skeleton-bar narrow"></div>
                <div class="skeleton-bar med"></div>
                <div class="skeleton-bar narrow"></div>
                <div style="display:flex; gap:0.3rem; justify-content:flex-end;">
                    <div class="skeleton-bar" style="width:40px; height:22px; border-radius:999px;"></div>
                    <div class="skeleton-bar" style="width:28px; height:22px; border-radius:999px;"></div>
                </div>
            </div>
        </div>
    `,
  ).join("");

  list.innerHTML = rows;
}

export async function refreshJobsManual() {
  const btn = document.getElementById("btn-refresh-jobs");
  const prevText = btn ? btn.textContent : "";
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Refreshing...";
  }

  try {
    await refreshJobs();
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = prevText || "Refresh";
    }
  }
}

// ─── Pollers ───

function syncPollers(jobs) {
  const activeIds = new Set(
    jobs.filter((j) => ["running", "pending", "discovering"].includes(j.status)).map((j) => j.id),
  );

  Object.keys(pollers).forEach((id) => {
    if (!activeIds.has(id)) {
      clearInterval(pollers[id]);
      delete pollers[id];
    }
  });

  activeIds.forEach((id) => {
    if (!pollers[id]) {
      const pollInterval =
        typeof window.DATAFORGE_POLL_JOB_INTERVAL === "number" ? window.DATAFORGE_POLL_JOB_INTERVAL : 3000;
      pollers[id] = setInterval(() => pollJob(id), pollInterval);
    }
  });
}

async function pollJob(id) {
  try {
    const r = await apiFetch(endpoints.job(id));
    if (!r.ok) return;
    const j = await r.json();

    // If looking at this job's results, refresh logs/progress
    if (currentView === "results") {
      if (currentJobId === id) {
        const logsPanel = document.getElementById("logs-panel");
        if (logsPanel && Array.isArray(j.logs) && j.logs.length) {
          logsPanel.classList.remove("hidden");
          renderLogs(j.logs);
        }

        const resProgWrap = document.getElementById("res-progress-wrap");
        if (j.progress_total > 0) {
          if (resProgWrap) resProgWrap.classList.remove("hidden");
          const pct = Math.round((j.progress_current / j.progress_total) * 100);
          const bar = document.getElementById("res-progress-bar");
          if (bar) bar.style.width = `${pct}%`;
          const progressText = document.getElementById("res-progress-text");
          if (progressText) progressText.textContent = `${pct}%`;
        } else {
          if (resProgWrap) resProgWrap.classList.add("hidden");
        }

        if (["completed", "degraded", "empty_result", "failed", "canceled"].includes(j.status)) {
          viewResults(id).catch((e) => console.warn("Auto-refresh results failed:", e));
        }
      }
    }

    if (["completed", "degraded", "empty_result", "failed", "canceled"].includes(j.status)) {
      clearInterval(pollers[id]);
      delete pollers[id];
      // Mark this job for a status-change flash on the next render
      _flashJobId = id;
      refreshJobs();
      // Skip the poller's terminal-state toast if the user just
      // initiated the action — they already saw the "Cancellation
      // requested" / "Job deleted" toast and a second one for the
      // same event would be noisy and confusing.
      if (_consumeRecentUserAction(id)) {
        return;
      }
      const truncate = (s, n) => {
        const str = String(s || "");
        return str.length > n ? str.slice(0, n) + "…" : str;
      };
      if (j.status === "completed") toast(`"${truncate(j.name, 60)}" done — ${j.filtered_records} records`, "success");
      else if (j.status === "degraded")
        toast(`"${truncate(j.name, 60)}" finished with partial results — ${j.filtered_records} records`, "info");
      else if (j.status === "empty_result")
        toast(
          `"${truncate(j.name, 60)}" finished — 0 records. ${truncate(j.error, 80) || "Page may be empty, blocked, or require JS rendering."}`,
          "warning",
        );
      else if (j.status === "canceled") toast(`"${truncate(j.name, 60)}" canceled`, "info");
      else toast(`"${truncate(j.name, 60)}" failed: ${truncate(j.error, 80)}`, "error");
    }
  } catch (e) {
    console.warn("pollJob error:", e);
  }
}

// ─── CRUD ───

export async function cancelJob(id) {
  showConfirm("Cancel Job?", "Cancel this running job?", async () => {
    try {
      _markUserAction(id);
      const r = await apiFetch(endpoints.cancelJob(id), { method: "POST" });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data.detail || "Cancel failed");
      toast(data.message || "Cancellation requested", "info");
      refreshJobs();
    } catch (e) {
      toast(`Cancel failed: ${e.message}`, "error");
    }
  });
}

export async function deleteJob(id) {
  showConfirm("Delete Job?", "Move this job to the recycle bin?", async () => {
    try {
      _markUserAction(id);
      const r = await apiFetch(endpoints.deleteJob(id), { method: "DELETE" });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data.detail || "Delete failed");
      toast("Job deleted");
      refreshJobs();
    } catch (e) {
      toast(`Delete failed: ${e.message}`, "error");
    }
  });
}

export async function clearTerminalJobs() {
  const keepRecent = 5;
  showConfirm(
    "Clear Terminal Jobs?",
    `Remove completed/failed/canceled jobs, keeping the latest ${keepRecent}?`,
    async () => {
      try {
        const r = await apiFetch(endpoints.cleanupTerminalJobs(keepRecent), { method: "DELETE" });
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(data.detail || "Terminal cleanup failed");
        toast(data.message || "Terminal jobs cleared", "info");
        refreshJobs();
      } catch (e) {
        toast(`Cleanup failed: ${e.message}`, "error");
      }
    },
  );
}

// ─── Filtering ───

export function applyJobFilters(jobs) {
  const q = (document.getElementById("jobs-search")?.value || "").trim().toLowerCase();
  const status = (document.getElementById("jobs-status-filter")?.value || "all").toLowerCase();

  return jobs.filter((j) => {
    const name = String(j.name || "").toLowerCase();
    const topic = String(j.topic || "").toLowerCase();
    const statusMatch = status === "all" || getJobStatusGroup(j.status) === status;
    const queryMatch = !q || name.includes(q) || topic.includes(q);
    return statusMatch && queryMatch;
  });
}

export function onJobsFilterChanged() {
  const jobsSearch = document.getElementById("jobs-search");
  const jobsStatus = document.getElementById("jobs-status-filter");
  writeUIState({
    jobsSearch: jobsSearch ? jobsSearch.value : "",
    jobsStatus: jobsStatus ? jobsStatus.value : "all",
  });
  renderJobs(applyJobFilters(jobsCache));
}

// ─── Rendering ───

export function updateKPIs(jobs) {
  const total = document.getElementById("kpi-total");
  if (total) total.textContent = jobs.length;
  const running = document.getElementById("kpi-running");
  if (running)
    running.textContent = jobs.filter(
      (j) => j.status === "running" || j.status === "discovering" || j.status === "pending",
    ).length;
  const done = document.getElementById("kpi-done");
  if (done)
    done.textContent = jobs.filter((j) =>
      ["completed", "degraded", "empty_result", "canceled"].includes(j.status),
    ).length;
  const records = document.getElementById("kpi-records");
  if (records) records.textContent = jobs.reduce((s, j) => s + (j.filtered_records || 0), 0);
}

export function renderJobs(jobs) {
  const list = document.getElementById("jobs-list");
  const empty = document.getElementById("empty-state");
  if (!list) return;

  if (!jobs.length) {
    list.innerHTML = "";
    if (empty) {
      const titleEl = empty.querySelector(".empty-state-title") || empty.querySelector("h3");
      const descEl = empty.querySelector(".empty-state-desc") || empty.querySelector("p");
      const hasJobs = jobsCache.length > 0;
      if (titleEl) titleEl.textContent = hasJobs ? "No jobs match these filters" : "No jobs yet";
      if (descEl) {
        descEl.textContent = hasJobs ? "Adjust the status filter or search query." : "Create your first scrape job.";
      }
      list.appendChild(empty);
      empty.classList.remove("hidden");
    }
    return;
  }

  list.innerHTML = jobs
    .map((j) => {
      const isActive = ["pending", "discovering", "running"].includes(j.status);
      const hasProgress = j.progress_total > 0;
      const pct = hasProgress ? Math.round((j.progress_current / j.progress_total) * 100) : 0;
      const statusGroup = getJobStatusGroup(j.status);
      const issueCount = getIssueCount(j);

      const highlightClass =
        statusGroup === "completed"
          ? "completed-highlight"
          : statusGroup === "failed"
            ? "failed-highlight"
            : statusGroup === "running" || statusGroup === "queued"
              ? "running-highlight"
              : "";

      return `
            <div class="job-row${highlightClass ? " " + highlightClass : ""}" data-id="${attrStr(j.id)}">
                <div class="job-name-col">
                    <div class="job-name">
                        ${esc(j.name)}
                        <button class="btn-copy-id" data-action="copy-job-id" data-id="${attrStr(j.id)}" title="Copy job ID" aria-label="Copy job ID"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/></svg></button>
                        <span class="mode-tag">${j.mode === "auto" ? "auto" : "manual"}</span>
                    </div>
                    ${
                      isActive && hasProgress
                        ? `
                        <div class="job-progress-wrap">
                            <div class="job-progress-bar" style="width: ${pct}%"></div>
                            <span class="job-progress-text">${pct}%</span>
                        </div>
                    `
                        : ""
                    }
                </div>
                <div class="job-created">${esc(formatCreatedAt(j.created_at || j.created))}</div>
                <div class="job-urls">${Array.isArray(j.urls) ? j.urls.length : 0} URL${(Array.isArray(j.urls) ? j.urls.length : 0) !== 1 ? "s" : ""}</div>
                <div><span class="badge ${attrStr(statusGroup)}">${esc(formatJobStatus(j.status))}</span></div>
                <div class="job-records">${j.total_records > 0 ? `${esc(j.filtered_records)}` : "0"}</div>
                <div class="job-issues">${issueCount ? `${issueCount}` : "0"}</div>
                <div class="job-actions">
                    ${["completed", "degraded", "empty_result"].includes(j.status) ? `<button class="btn ghost small" data-action="view-results" data-id="${attrStr(j.id)}">View</button>` : ""}
                    ${isActive ? `<button class="btn warn-ghost small" data-action="cancel-job" data-id="${attrStr(j.id)}">Cancel</button>` : ""}
                    ${("failed" === j.status || "error" === j.status) ? renderFailureBadge(j) : ""}
                    <button class="btn danger-ghost small" data-action="delete-job" data-id="${attrStr(j.id)}"><span data-icon="x" data-size="14"></span></button>
                </div>
            </div>
        `;
    })
    .join("");

  // Attach failure explanation tooltips to failed job rows
  jobs.forEach((j) => {
    const row = list.querySelector(`[data-id="${CSS.escape(j.id)}"]`);
    if (row) attachFailureExplanationToJobRow(row, j);
  });

  // Init interactive failure badges (click-to-toast)
  initFailureBadges();

  // Apply status-change flash animation if a job just transitioned
  if (_flashJobId) {
    const flashRow = list.querySelector(`[data-id="${CSS.escape(_flashJobId)}"]`);
    if (flashRow) {
      flashRow.classList.add("status-change");
      flashRow.addEventListener(
        "animationend",
        () => {
          flashRow.classList.remove("status-change");
        },
        { once: true },
      );
    }
    _flashJobId = null;
  }
}
