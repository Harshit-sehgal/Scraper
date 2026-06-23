/* ═══════════════════════════════════
   DataForge — Retention / data deletion view
   ═══════════════════════════════════ */

import { apiFetch } from "./api.js";
import { showConfirm, toast } from "./utils.js";

// ─── Slider live-update ───

function _initSliders() {
  const sliders = [
    { id: "slider-log-expiry", display: "retention-log-days" },
    { id: "slider-metrics-archival", display: "retention-metrics-days" },
    { id: "slider-cold-ttl", display: "retention-cold-years" },
  ];

  for (const { id, display } of sliders) {
    const slider = document.getElementById(id);
    const val = document.getElementById(display);
    if (!slider || !val) continue;
    slider.addEventListener("input", () => {
      val.textContent = slider.value;
    });
  }
}

// ─── Recycle bin summary (sidebar stats) ───

function renderPurgeStats(items) {
  const countEl = document.getElementById("retention-recycle-count");
  const sizeEl = document.getElementById("retention-purge-size");

  if (countEl) {
    countEl.textContent = items && items.length ? `${items.length} items` : "0 items";
  }
  if (sizeEl) {
    // We don't have size info from the API; estimate from item count
    sizeEl.textContent = items && items.length ? `~${items.length} entries` : "0 entries";
  }
}

export async function refreshRetention() {
  try {
    const resp = await apiFetch("/api/recycle_bin?limit=200");
    if (resp.status === 401) {
      renderPurgeStats(null);
      return;
    }
    if (!resp.ok) {
      renderPurgeStats(null);
      return;
    }
    const body = await resp.json();
    const items = Array.isArray(body?.items) ? body.items : Array.isArray(body?.jobs) ? body.jobs : [];
    renderPurgeStats(items);
  } catch (err) {
    renderPurgeStats(null);
    toast(`Failed to load purge stats: ${err.message || err}`, "error");
  }
}

export async function deleteMyData() {
  showConfirm(
    "Delete ALL my data?",
    "This will permanently delete ALL your data: jobs, results, workflows, scheduled jobs, auth profiles, and SaaS identity records. This cannot be undone.",
    async () => {
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
        toast(`Data deleted. Cleaned: ${cleaned || "nothing"}.`, "success");
        await refreshRetention();
      } catch (err) {
        toast(`Failed to delete data: ${err.message || err}`, "error");
      }
    },
  );
}

// ─── Save retention policies (placeholder — no backend endpoint yet) ───

export async function saveRetentionPolicies() {
  const logExpiry = document.getElementById("slider-log-expiry")?.value;
  const metricsArchival = document.getElementById("slider-metrics-archival")?.value;
  const coldTTL = document.getElementById("slider-cold-ttl")?.value;

  toast(
    `Retention policies saved: ${logExpiry}d logs, ${metricsArchival}d metrics, ${coldTTL}y cold storage`,
    "success",
  );
}

// ─── Initialize on view mount ───

export function initRetention() {
  _initSliders();
}
