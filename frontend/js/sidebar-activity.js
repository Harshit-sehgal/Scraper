/* ═══════════════════════════════════
   DataForge — Sidebar Activity Feed
   ═══════════════════════════════════
   Lightweight activity feed shown at the bottom of the sidebar.
   Displays up to 3 most recent job status changes based on
   the already-fetched jobs list (no extra API calls). */

const MAX_ITEMS = 3;

/**
 * Update the sidebar activity feed from the current jobs data.
 * @param {Array} jobs — array of job objects from GET /api/jobs
 */
export function updateSidebarActivity(jobs) {
  const list = document.getElementById("sidebar-activity-list");
  if (!list) return;

  if (!jobs || jobs.length === 0) {
    list.innerHTML =
      '<span class="sidebar-activity-item">No recent activity</span>';
    return;
  }

  // Take the 3 most recent jobs by created_at / started_at
  const recent = jobs
    .slice()
    .sort((a, b) => {
      const ta = a.started_at || a.created_at || 0;
      const tb = b.started_at || b.created_at || 0;
      return tb - ta;
    })
    .slice(0, MAX_ITEMS);

  list.innerHTML = recent
    .map((job) => {
      const status = job.status || "unknown";
      const name = _truncate(job.intent || job.id || "Job", 20);
      const time = _formatTimeAgo(job.started_at || job.created_at);
      return `<span class="sidebar-activity-item" title="${_esc(status)}: ${_esc(name)}">
        <span class="activity-dot"></span>
        <span>${_esc(name)}</span>
        <span class="activity-time">${time}</span>
      </span>`;
    })
    .join("");
}

function _truncate(s, max) {
  if (!s) return "";
  return s.length > max ? s.slice(0, max - 1) + "…" : s;
}

function _formatTimeAgo(ts) {
  if (!ts) return "";
  const diff = Math.floor((Date.now() - ts * 1000) / 1000);
  if (diff < 5) return "now";
  if (diff < 60) return `${diff}s`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
  return `${Math.floor(diff / 86400)}d`;
}

function _esc(s) {
  if (!s) return "";
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}
