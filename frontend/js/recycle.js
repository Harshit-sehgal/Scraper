/* ═══════════════════════════════════════════
   DataForge — Recycle Bin
   ═══════════════════════════════════════════
   Supports single and batch operations:
   restore, hard-delete, clear-all.
   ============================================ */

import { esc, attrStr, toast, showConfirm } from "./utils.js";
import { API, apiFetch } from "./api.js";

let _selected = new Set();
let _cachedJobs = [];

// ─── Refresh ───

export async function refreshRecycleBin() {
  try {
    const r = await apiFetch(`${API}/api/recycle_bin`);
    if (!r.ok) throw new Error("Failed to load recycle bin");
    const data = await r.json();
    _cachedJobs = Array.isArray(data.jobs) ? data.jobs : [];
    _selected = new Set();
    _render();
  } catch (e) {
    toast(`Failed to load recycle bin: ${e.message}`, "error");
  }
}

// ─── Rendering ───

function _formatTimestamp(value) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  return (
    d.toLocaleString([], {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    }) + " UTC"
  );
}

function _render() {
  const tbody = document.getElementById("recycle-list");
  const emptyRow = document.getElementById("empty-recycle-state-row");
  const rangeEl = document.getElementById("recycle-pagination-range");

  if (!tbody) return;

  if (_cachedJobs.length === 0) {
    tbody.innerHTML = "";
    if (emptyRow) {
      tbody.appendChild(emptyRow);
      const empty = emptyRow.querySelector("#empty-recycle-state");
      if (empty) empty.classList.remove("hidden");
    }
    if (rangeEl) rangeEl.textContent = "Showing 0 entries";
    return;
  }

  // Use first URL as target for display, matching stitch "Target URL" column
  tbody.innerHTML = _cachedJobs
    .map((j) => {
      const targetUrl = Array.isArray(j.urls) && j.urls.length > 0 ? j.urls[0] : j.name;
      const statusBadgeClass = j.status === "failed" || j.status === "error" ? "badge badge-failed" : "badge canceled";
      const statusLabel = j.status === "failed" || j.status === "error" ? "Failed Purge" : "Soft Deleted";

      return `
        <tr data-job-id="${attrStr(j.id)}">
          <td class="col-recycle-id" data-label="Job ID">${esc((j.id || "").slice(0, 12))}</td>
          <td class="col-recycle-deleted" data-label="Deleted At">${esc(_formatTimestamp(j.deleted_at || j.updated_at))}</td>
          <td class="col-recycle-url" data-label="Target URL" title="${esc(targetUrl)}">${esc(targetUrl)}</td>
          <td class="col-recycle-status" data-label="Status"><span class="${statusBadgeClass}">${esc(statusLabel)}</span></td>
          <td class="col-recycle-actions" data-label="Actions">
            <div class="hover-actions">
              <button class="action-btn" data-action="restore-job" data-id="${attrStr(j.id)}" title="Restore Job" aria-label="Restore job">
                <span class="material-symbols-outlined" style="font-size:18px;">restore</span>
              </button>
              <button class="action-btn action-danger" data-action="hard-delete-job" data-id="${attrStr(j.id)}" title="Delete Permanently" aria-label="Delete permanently">
                <span class="material-symbols-outlined" style="font-size:18px;">delete_forever</span>
              </button>
            </div>
          </td>
        </tr>`;
    })
    .join("");

  // Pagination range
  if (rangeEl) {
    rangeEl.textContent = `Showing 1 to ${_cachedJobs.length} of ${_cachedJobs.length} entries`;
  }
}

function _updateBatchBar() {
  const bar = document.getElementById("recycle-batch-bar");
  const actionEls = document.getElementById("recycle-batch-actions");
  const countEl = document.getElementById("recycle-selected-count");
  if (!bar) return;
  if (_cachedJobs.length === 0) {
    bar.style.display = "none";
    return;
  }
  bar.style.display = "flex";
  if (countEl) countEl.textContent = `${_selected.size} selected`;
  if (actionEls) {
    const btns = actionEls.querySelectorAll("button");
    btns.forEach((btn) => {
      btn.disabled = _selected.size === 0;
    });
  }
}

// ─── Selection handlers ───

export function handleRecycleSelectAll(checked) {
  if (checked) {
    _cachedJobs.forEach((j) => _selected.add(j.id));
  } else {
    _selected.clear();
  }
  _render();
}

export function handleRecycleSelectItem(id, checked) {
  if (checked) {
    _selected.add(id);
  } else {
    _selected.delete(id);
  }
  _render();
}

// ─── Single-item operations ───

export async function restoreJob(id) {
  try {
    const r = await apiFetch(`${API}/api/recycle_bin/${id}/restore`, { method: "POST" });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.detail || "Restore failed");
    toast("Job restored");
    refreshRecycleBin();
  } catch (e) {
    toast(`Restore failed: ${e.message}`, "error");
  }
}

export async function hardDeleteJob(id) {
  showConfirm(
    "Delete Forever?",
    "Permanently delete this job from the recycle bin? This cannot be undone.",
    async () => {
      try {
        const r = await apiFetch(`${API}/api/recycle_bin/${id}`, { method: "DELETE" });
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(data.detail || "Permanent delete failed");
        toast("Job permanently deleted", "success");
        _selected.delete(id);
        refreshRecycleBin();
      } catch (e) {
        toast(`Permanent delete failed: ${e.message}`, "error");
      }
    },
  );
}

// ─── Batch operations ───

export async function batchRestore() {
  const ids = [..._selected];
  if (ids.length === 0) {
    toast("No jobs selected", "info");
    return;
  }
  showConfirm(
    `Restore ${ids.length} job${ids.length !== 1 ? "s" : ""}?`,
    `Restore ${ids.length} job${ids.length !== 1 ? "s" : ""} from the recycle bin?`,
    async () => {
      let success = 0;
      for (const id of ids) {
        try {
          const r = await apiFetch(`${API}/api/recycle_bin/${id}/restore`, { method: "POST" });
          if (r.ok) success++;
        } catch {
          // Continue with remaining
        }
      }
      toast(
        `Restored ${success} of ${ids.length} job${ids.length !== 1 ? "s" : ""}`,
        success > 0 ? "success" : "error",
      );
      _selected = new Set();
      refreshRecycleBin();
    },
  );
}

export async function batchHardDelete() {
  const ids = [..._selected];
  if (ids.length === 0) {
    toast("No jobs selected", "info");
    return;
  }
  showConfirm(
    `Delete ${ids.length} job${ids.length !== 1 ? "s" : ""} forever?`,
    `Permanently delete ${ids.length} job${ids.length !== 1 ? "s" : ""}? This cannot be undone.`,
    async () => {
      let success = 0;
      for (const id of ids) {
        try {
          const r = await apiFetch(`${API}/api/recycle_bin/${id}`, { method: "DELETE" });
          if (r.ok) success++;
        } catch {
          // Continue with remaining
        }
      }
      toast(
        `Deleted ${success} of ${ids.length} job${ids.length !== 1 ? "s" : ""} permanently`,
        success > 0 ? "success" : "error",
      );
      _selected = new Set();
      refreshRecycleBin();
    },
  );
}

// ─── Clear all ───

export async function clearRecycleBin() {
  showConfirm("Empty Recycle Bin?", "Empty entire recycle bin? This cannot be undone.", async () => {
    try {
      const r = await apiFetch(`${API}/api/recycle_bin`, { method: "DELETE" });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data.detail || "Failed to clear recycle bin");
      toast(data.message || "Recycle bin cleared", "info");
      _selected = new Set();
      refreshRecycleBin();
    } catch (e) {
      toast(`Recycle clear failed: ${e.message}`, "error");
    }
  });
}
