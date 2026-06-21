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

function _render() {
  const list = document.getElementById("recycle-list");
  const empty = document.getElementById("empty-recycle-state");
  if (!list) return;

  if (_cachedJobs.length === 0) {
    list.innerHTML = "";
    if (empty) {
      empty.classList.remove("hidden");
      list.appendChild(empty);
    }
    _updateBatchBar();
    return;
  }
  if (empty) empty.classList.add("hidden");

  const allSelected = _cachedJobs.length > 0 && _cachedJobs.every((j) => _selected.has(j.id));

  list.innerHTML = `
    <div class="recycle-batch-bar" id="recycle-batch-bar">
      <label class="recycle-check-label">
        <input type="checkbox" class="recycle-select-all" ${allSelected ? "checked" : ""}
          data-action="recycle-select-all" aria-label="Select all jobs" />
        <span>Select all (${_cachedJobs.length})</span>
      </label>
      <div class="recycle-batch-actions" id="recycle-batch-actions">
        <span class="recycle-selected-count" id="recycle-selected-count">
          ${_selected.size} selected
        </span>
        <button type="button" class="btn ghost small" data-action="recycle-batch-restore"
          ${_selected.size === 0 ? "disabled" : ""}>
          Restore selected
        </button>
        <button type="button" class="btn danger-ghost small" data-action="recycle-batch-delete"
          ${_selected.size === 0 ? "disabled" : ""}>
          Delete selected
        </button>
      </div>
    </div>
    ${_cachedJobs.map((j) => {
      const checked = _selected.has(j.id) ? "checked" : "";
      return `
        <div class="job-row recycle-row ${checked ? "selected" : ""}" data-job-id="${attrStr(j.id)}">
          <div class="recycle-check-col">
            <input type="checkbox" class="recycle-check-item" data-id="${attrStr(j.id)}"
              ${checked} aria-label="Select ${esc(j.name)}" />
          </div>
          <div class="job-name recycle-name">${esc(j.name)}</div>
          <div><span class="badge ${attrStr(j.status)}">${esc(j.status)}</span></div>
          <div class="job-records">${j.total_records > 0 ? esc(String(j.filtered_records)) : "—"}</div>
          <div class="job-actions">
            <button class="btn ghost small" data-action="restore-job" data-id="${attrStr(j.id)}">Restore</button>
            <button class="btn danger-ghost small" data-action="hard-delete-job" data-id="${attrStr(j.id)}">Delete Forever</button>
          </div>
        </div>`;
    }).join("")}`;

  _updateBatchBar();
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
      toast(`Restored ${success} of ${ids.length} job${ids.length !== 1 ? "s" : ""}`, success > 0 ? "success" : "error");
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
      toast(`Deleted ${success} of ${ids.length} job${ids.length !== 1 ? "s" : ""} permanently`, success > 0 ? "success" : "error");
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
