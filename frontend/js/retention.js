/* ═══════════════════════════════════
   DataForge — Retention / data deletion view
   ═══════════════════════════════════ */

import { apiFetch } from "./api.js";
import { toast } from "./utils.js";

function formatTime(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString();
  } catch {
    return iso;
  }
}

function renderRecycleSummary(items) {
  const el = document.getElementById("retention-recycle-summary");
  if (!el) return;
  el.innerHTML = "";
  if (!items || items.length === 0) {
    el.innerHTML = '<p class="subtle">Recycle bin is empty.</p>';
    return;
  }
  const total = items.length;
  const oldest = items.reduce((acc, x) => {
    const t = x.deleted_at || x.updated_at || x.created_at || "";
    if (!acc || (t && t < acc)) return t;
    return acc;
  }, "");
  const newest = items.reduce((acc, x) => {
    const t = x.deleted_at || x.updated_at || x.created_at || "";
    if (!acc || (t && t > acc)) return t;
    return acc;
  }, "");
  const stats = document.createElement("div");
  stats.className = "retention-stats";
  stats.innerHTML = `
    <div class="kpi-row">
      <div class="kpi"><span class="kpi-val">${total}</span><span class="kpi-label">Items in bin</span></div>
      <div class="kpi"><span class="kpi-val">${oldest ? formatTime(oldest) : "—"}</span><span class="kpi-label">Oldest</span></div>
      <div class="kpi"><span class="kpi-val">${newest ? formatTime(newest) : "—"}</span><span class="kpi-label">Newest</span></div>
    </div>
    <p class="subtle">Items are auto-purged after 30 days.</p>
  `;
  el.appendChild(stats);
}

export async function refreshRetention() {
  try {
    const resp = await apiFetch("/api/recycle_bin?limit=200");
    if (resp.status === 401) {
      renderRecycleSummary(null);
      const el = document.getElementById("retention-recycle-summary");
      if (el) el.innerHTML = '<p class="subtle">Sign in to view your recycle bin.</p>';
      return;
    }
    if (!resp.ok) {
      renderRecycleSummary(null);
      return;
    }
    const body = await resp.json();
    const items = Array.isArray(body?.items) ? body.items : [];
    renderRecycleSummary(items);
  } catch (err) {
    renderRecycleSummary(null);
    toast(`Failed to load recycle bin: ${err.message || err}`, "error");
  }
}

export async function deleteMyData() {
  if (
    !confirm(
      "This will permanently delete ALL your data: jobs, results, workflows, scheduled jobs, auth profiles, and SaaS identity records. This cannot be undone. Continue?",
    )
  ) {
    return;
  }
  try {
    const resp = await apiFetch("/api/user/data", { method: "DELETE" });
    if (!resp.ok) {
      const detail = (await resp.json().catch(() => ({}))).detail || `HTTP ${resp.status}`;
      toast(`Failed to delete data: ${detail}`, "error");
      return;
    }
    const body = await resp.json();
    const summary = body?.summary || {};
    const cleaned = Object.entries(summary)
      .filter(([_, v]) => typeof v === "number" && v > 0)
      .map(([k, v]) => `${v} ${k.replace(/_/g, " ")}`)
      .join(", ");
    toast(`Data deleted. Cleaned: ${cleaned || "nothing"}.`, "ok");
    await refreshRetention();
  } catch (err) {
    toast(`Failed to delete data: ${err.message || err}`, "error");
  }
}
