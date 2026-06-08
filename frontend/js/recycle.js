/* ═══════════════════════════════════════════
   DataForge — Recycle Bin
   ═══════════════════════════════════════════ */

import { esc, attrStr, toast, showConfirm } from "./utils.js";
import { API, apiFetch } from "./api.js";

// ─── Refresh ───

export async function refreshRecycleBin() {
  try {
    const r = await apiFetch(`${API}/api/recycle_bin`);
    if (!r.ok) throw new Error("Failed to load recycle bin");
    const data = await r.json();
    const jobs = Array.isArray(data.jobs) ? data.jobs : [];

    const list = document.getElementById("recycle-list");
    const empty = document.getElementById("empty-recycle-state");

    if (!jobs.length) {
      list.innerHTML = "";
      list.appendChild(empty);
      empty.classList.remove("hidden");
      return;
    }

    list.innerHTML = jobs
      .map(
        (j) => `
            <div class="job-row recycle-row">
                <div class="job-name recycle-name">
                    ${esc(j.name)}
                </div>
                <div><span class="badge ${attrStr(j.status)}">${esc(j.status)}</span></div>
                <div class="job-records">${j.total_records > 0 ? `${esc(j.filtered_records)}` : "—"}</div>
                <div class="job-actions">
                    <button class="btn ghost small" data-action="restore-job" data-id="${attrStr(j.id)}">Restore</button>
                    <button class="btn danger-ghost small" data-action="hard-delete-job" data-id="${attrStr(j.id)}">Delete Forever</button>
                </div>
            </div>
        `,
      )
      .join("");
  } catch (e) {
    toast(`Failed to load recycle bin: ${e.message}`, "error");
  }
}

// ─── Restore ───

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

// ─── Hard Delete ───

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
        refreshRecycleBin();
      } catch (e) {
        toast(`Permanent delete failed: ${e.message}`, "error");
      }
    },
  );
}

// ─── Clear All ───

export async function clearRecycleBin() {
  showConfirm("Empty Recycle Bin?", "Empty entire recycle bin? This cannot be undone.", async () => {
    try {
      const r = await apiFetch(`${API}/api/recycle_bin`, { method: "DELETE" });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data.detail || "Failed to clear recycle bin");
      toast(data.message || "Recycle bin cleared", "info");
      refreshRecycleBin();
    } catch (e) {
      toast(`Recycle clear failed: ${e.message}`, "error");
    }
  });
}
