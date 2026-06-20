/* ═══════════════════════════════════════════
   DataForge — Results Viewing & Export
   ═══════════════════════════════════════════ */

import { esc, attrStr, toast, showConfirm } from "./utils.js";
import { apiFetch, endpoints } from "./api.js";
import { switchView } from "./views.js";
import { refreshJobs } from "./jobs.js";

// ─── State ───

export let currentJobId = null;
let currentResultsCache = [];

export function setCurrentJobId(id) {
  currentJobId = id;
}

export function getExportUrl(format, id) {
  if (format === "csv") return endpoints.exportCsv(id);
  if (format === "json") return endpoints.exportJson(id);
  if (format === "excel") return endpoints.exportExcel(id);
  throw new Error(`Unsupported export format: ${format}`);
}

// ─── View Results ───

function renderResultsSkeleton() {
  // Show skeleton loading state in the results view
  const title = document.getElementById("res-title");
  if (title) title.textContent = "Loading...";
  const meta = document.getElementById("res-meta");
  if (meta) meta.textContent = "Fetching results...";
  const exportGrp = document.getElementById("export-group");
  if (exportGrp) exportGrp.style.display = "none";
  const warnBanner = document.getElementById("result-warning");
  if (warnBanner) warnBanner.style.display = "none";
  const lineage = document.getElementById("lineage-summary");
  if (lineage) lineage.style.display = "none";
  const aiPanel = document.getElementById("ai-insight-panel");
  if (aiPanel) aiPanel.classList.add("hidden");
  const logsPanel = document.getElementById("logs-panel");
  if (logsPanel) logsPanel.classList.add("hidden");
  const qualityPanel = document.getElementById("quality-panel");
  if (qualityPanel) qualityPanel.classList.add("hidden");
  const progressWrap = document.getElementById("res-progress-wrap");
  if (progressWrap) progressWrap.classList.add("hidden");

  const thead = document.getElementById("res-thead");
  const tbody = document.getElementById("res-tbody");
  if (thead)
    thead.innerHTML = `
        <tr>
            ${["Column 1", "Column 2", "Column 3", "Column 4", "Column 5"]
              .map(
                (_, i) =>
                  `<th style="min-width:${100 + i * 20}px"><div class="skeleton-bar" style="width:${70 + i * 10}%;height:10px;margin:2px 0"></div></th>`,
              )
              .join("")}
        </tr>`;
  if (tbody)
    tbody.innerHTML = Array.from(
      { length: 6 },
      (_, i) => `
        <tr>
            ${Array.from(
              { length: 5 },
              (_, j) => `
                <td><div class="skeleton-bar" style="width:${40 + (i + j) * 10}%;height:10px;margin:4px 0"></div></td>
            `,
            ).join("")}
        </tr>`,
    ).join("");

  const label = document.getElementById("result-count-label");
  if (label) label.textContent = "loading...";
}

export async function viewResults(id) {
  currentJobId = id;
  switchView("results");
  renderResultsSkeleton();
  try {
    const r = await apiFetch(endpoints.job(id));
    if (!r.ok) throw new Error(`Failed to load results: ${r.status}`);
    const j = await r.json();
    // Guard against stale responses: if the user has since clicked
    // another job's "View Results", ``currentJobId`` will have been
    // updated and this response is no longer relevant.
    if (currentJobId !== id) return;
    const resTitle = document.getElementById("res-title");
    if (resTitle) resTitle.textContent = j.name;
    const resMeta = document.getElementById("res-meta");
    if (resMeta) resMeta.textContent = `${j.filtered_records} records extracted (${j.total_records} total)`;

    // Warning banner
    const warnBanner = document.getElementById("result-warning");
    if (warnBanner) {
      if (j.status === "empty_result") {
        warnBanner.textContent = `No records extracted. ${j.error || "The page may be session-bound, blocked, empty, or require JavaScript rendering."}`;
        warnBanner.classList.remove("banner-info", "banner-success", "banner-error");
        warnBanner.classList.add("banner", "banner-warning");
        warnBanner.style.display = "block";
      } else if (j.status === "degraded") {
        warnBanner.textContent = j.error || "Some URLs produced no results.";
        warnBanner.classList.remove("banner-info", "banner-success", "banner-error");
        warnBanner.classList.add("banner", "banner-warning");
        warnBanner.style.display = "block";
      } else {
        warnBanner.style.display = "none";
      }
    }

    // Lineage Summary
    renderLineageSummary(j);

    const exportGrp = document.getElementById("export-group");
    if (exportGrp) exportGrp.style.display = Array.isArray(j.results) && j.results.length ? "flex" : "none";
    const tableWrap = document.querySelector("#view-results .table-wrap");
    if (tableWrap) tableWrap.scrollLeft = 0;

    // AI Insight
    const aiPanel = document.getElementById("ai-insight-panel");
    if (aiPanel) {
      if (j.analysis) {
        aiPanel.classList.remove("hidden");
        const aiText = document.getElementById("ai-insight-text");
        if (aiText) aiText.textContent = j.analysis;
      } else {
        aiPanel.classList.add("hidden");
      }
    }

    // Logs
    const logsPanel = document.getElementById("logs-panel");
    if (logsPanel && Array.isArray(j.logs) && j.logs.length) {
      logsPanel.classList.remove("hidden");
      renderLogs(j.logs);
    } else if (logsPanel) {
      logsPanel.classList.add("hidden");
    }

    // Quality Report
    renderQualityPanel(j);

    // Progress
    const isActive = ["pending", "discovering", "running"].includes(j.status);
    const resProgWrap = document.getElementById("res-progress-wrap");
    if (isActive && j.progress_total > 0) {
      if (resProgWrap) resProgWrap.classList.remove("hidden");
      const pct = Math.round((j.progress_current / j.progress_total) * 100);
      const bar = document.getElementById("res-progress-bar");
      if (bar) bar.style.width = `${pct}%`;
      const progressText = document.getElementById("res-progress-text");
      if (progressText) progressText.textContent = `${pct}%`;
    } else {
      if (resProgWrap) resProgWrap.classList.add("hidden");
    }

    currentResultsCache = Array.isArray(j.results) ? j.results : [];
    const resultSearch = document.getElementById("inp-result-search");
    if (resultSearch) resultSearch.value = "";
    renderFilteredResults();
    syncResultsScrollSlider();
  } catch (_e) {
    toast("Failed to load results", "error");
    const thead = document.getElementById("res-thead");
    const tbody = document.getElementById("res-tbody");
    if (thead) thead.innerHTML = "";
    if (tbody) tbody.innerHTML = '<tr><td class="empty-cell" colspan="100">Failed to load results</td></tr>';
  }
}

// ─── Lineage Summary ───

function renderLineageSummary(j) {
  const el = document.getElementById("lineage-summary");
  if (!el) return;
  const resultsList = Array.isArray(j.results) ? j.results : [];
  if (resultsList.length) {
    const states = new Map();
    resultsList.forEach((r) => {
      const lin = r._acquisition_lineage;
      if (lin && lin.state) {
        states.set(lin.state, (states.get(lin.state) || 0) + 1);
      }
    });
    if (states.size) {
      const parts = [];
      states.forEach((count, state) => {
        parts.push(`${esc(state)}: ${count}`);
      });
      el.innerHTML = `📡 <strong>Acquisition:</strong> ${parts.join(" · ")}`;
      el.style.display = "block";
    } else {
      el.style.display = "none";
    }
  } else {
    el.style.display = "none";
  }
}

// ─── Quality Panel ───

function renderQualityPanel(j) {
  const qualityPanel = document.getElementById("quality-panel");
  const qualityText = document.getElementById("quality-text");
  if (j.quality_report && typeof j.quality_report === "object") {
    if (qualityPanel) qualityPanel.classList.remove("hidden");
    const qr = j.quality_report;
    const radius = qr.radius || {};
    const integrity = qr.type_integrity || {};
    const sourceBreakdown = qr.source_breakdown || {};
    const sourceAI = qr.ai_source_prediction || {};
    const aiStruct = qr.ai_structuring || {};
    const reclean = qr.reclean || {};
    const overall = Number.isFinite(Number(qr.overall_score)) ? Number(qr.overall_score).toFixed(3) : "n/a";
    const radiusPart = radius.applied
      ? `Radius kept ${radius.kept}/${(radius.kept || 0) + (radius.dropped || 0)} records`
      : `Radius not applied (${radius.reason || "not configured"})`;
    const noiseRemoved = (aiStruct.noise_rows_removed || 0) + ((reclean.ai_structuring || {}).noise_rows_removed || 0);
    if (qualityText)
      qualityText.textContent = `Overall: ${overall} | Average score: ${qr.avg_record_score || 0} | Final avg: ${qr.avg_final_record_score || 0} | Below threshold: ${qr.records_below_threshold || 0}. Type mismatches: ${integrity.total_type_mismatches || 0} across ${integrity.records_with_type_mismatch || 0} records. Sources: official ${sourceBreakdown.official || 0}, directory ${sourceBreakdown.directory || 0}, social ${sourceBreakdown.social || 0}. Source-level AI mapping: ${sourceAI.records_ai_structured || 0}/${sourceAI.records_processed || 0} rows. AI structuring: ${aiStruct.ai_chunks || 0}/${aiStruct.total_chunks || 0} chunks. Noise rows removed: ${noiseRemoved}. ${radiusPart}. Re-clean: ${reclean.applied ? `${reclean.before_records || 0} -> ${reclean.after_records || 0}` : "not run"}.`;
  } else {
    if (qualityPanel) qualityPanel.classList.add("hidden");
    if (qualityText) qualityText.textContent = "";
  }
}

// ─── Logs ───

export function renderLogs(logs) {
  const container = document.getElementById("logs-container");
  if (!container) return;

  const sorted = [...logs]
    .filter((log) => log && log.timestamp != null && !isNaN(new Date(log.timestamp).getTime()))
    .sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));

  container.innerHTML = sorted
    .map((log) => {
      const time = new Date(log.timestamp).toLocaleTimeString([], {
        hour12: false,
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
      return `
            <div class="log-entry">
                <span class="log-time">[${time}]</span>
                <span class="log-msg ${attrStr(log.level || "info")}">${esc(log.message)}</span>
            </div>
        `;
    })
    .join("");

  container.scrollTop = container.scrollHeight;
}

// ─── Table Rendering ───

export function applyResultSearch(rows) {
  const q = (document.getElementById("inp-result-search")?.value || "").trim().toLowerCase();
  if (!q) return rows;

  return rows.filter((row) =>
    Object.values(row || {}).some((value) => {
      const normalized = Array.isArray(value) ? value.join(" ") : value;
      return String(normalized ?? "")
        .toLowerCase()
        .includes(q);
    }),
  );
}

export function renderFilteredResults() {
  const filtered = applyResultSearch(currentResultsCache);
  const emptyMessage = currentResultsCache.length && !filtered.length ? "No matching rows for this filter" : "";

  renderTable(filtered, emptyMessage);

  const label = document.getElementById("result-count-label");
  if (label) {
    label.textContent = `${filtered.length} of ${currentResultsCache.length} rows`;
  }

  syncResultsScrollSlider();
}

export function renderTable(results, emptyMessage = "No results") {
  const thead = document.getElementById("res-thead");
  const tbody = document.getElementById("res-tbody");
  if (!thead || !tbody) return;
  if (!results.length) {
    thead.innerHTML = "";
    if (emptyMessage) {
      tbody.innerHTML = `<tr><td class="empty-cell" colspan="100">${esc(emptyMessage)}</td></tr>`;
      return;
    }
    tbody.innerHTML = `
      <tr>
        <td class="empty-cell" colspan="100">
          <div class="empty-result">
            <strong>No records were extracted.</strong>
            <p>Possible reasons:</p>
            <ul>
              <li>the selectors did not match</li>
              <li>the page loaded content dynamically</li>
              <li>the website blocked automated access</li>
              <li>the schema fields were too specific</li>
            </ul>
          </div>
        </td>
      </tr>
    `;
    return;
  }
  const preferredOrder = [
    "company_name",
    "email",
    "phone",
    "website",
    "address",
    "record_score",
    "source_type",
    "source_trust_score",
    "source_url",
    "scraped_at",
  ];
  const seen = new Set();
  const discoveredKeys = [];
  results.forEach((row) => {
    Object.keys(row || {}).forEach((k) => {
      if (k.startsWith("_")) return;
      if (!seen.has(k)) {
        seen.add(k);
        discoveredKeys.push(k);
      }
    });
  });
  const keys = [
    ...preferredOrder.filter((k) => seen.has(k)),
    ...discoveredKeys.filter((k) => !preferredOrder.includes(k)),
  ];
  thead.innerHTML = `<tr>${keys.map((k) => `<th>${esc(k)}</th>`).join("")}</tr>`;
  tbody.innerHTML = results
    .map((row) => {
      const isUnstable = row._is_unstable === true;
      const rowClass = isUnstable ? "unstable-row" : "";
      return `<tr class="${rowClass}">${keys
        .map((k) => {
          let v = row[k];
          if (v !== null && typeof v === "object" && !Array.isArray(v)) {
            v = JSON.stringify(v);
          }
          if (Array.isArray(v)) v = v.join(", ");
          if (v === null || v === undefined || v === "{}" || v === "") v = "—";
          const text = String(v);
          return `<td data-raw="${attrStr(text)}" title="${attrStr(text)}">${esc(text)}</td>`;
        })
        .join("")}</tr>`;
    })
    .join("");
}

// ─── Scroll Slider ───

export function syncResultsScrollSlider() {
  const wrap = document.querySelector("#view-results .table-wrap");
  const row = document.getElementById("results-scrollbar");
  const slider = document.getElementById("results-scroll-slider");
  const pos = document.getElementById("results-scroll-pos");
  if (!wrap || !row || !slider || !pos) return;

  const maxScroll = Math.max(0, wrap.scrollWidth - wrap.clientWidth);
  if (maxScroll <= 1) {
    row.classList.add("hidden");
    slider.max = "0";
    slider.value = "0";
    pos.textContent = "0%";
    return;
  }

  row.classList.remove("hidden");
  slider.max = String(maxScroll);
  slider.value = String(Math.min(maxScroll, Math.max(0, Math.round(wrap.scrollLeft))));
  const pct = Math.round((Number(slider.value) / maxScroll) * 100);
  pos.textContent = `${pct}%`;
}

export function onResultsSliderInput() {
  const wrap = document.querySelector("#view-results .table-wrap");
  const slider = document.getElementById("results-scroll-slider");
  if (!wrap || !slider) return;
  wrap.scrollLeft = Number(slider.value || 0);
  syncResultsScrollSlider();
}

export function onResultsTableScroll() {
  syncResultsScrollSlider();
}

// ─── Cell Copy ───

export async function onResultsCellDoubleClick(e) {
  const cell = e.target.closest("td");
  if (!cell) return;

  const value = String(cell.getAttribute("data-raw") || cell.textContent || "").trim();
  if (!value || value === "—") return;

  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(value);
    } else {
      const t = document.createElement("textarea");
      t.value = value;
      t.style.position = "fixed";
      t.style.left = "-9999px";
      document.body.appendChild(t);
      t.select();
      document.execCommand("copy");
      t.remove();
    }
    toast("Copied cell value", "success");
  } catch {
    toast("Copy failed", "error");
  }
}

export async function copySampleRow() {
  const sample = currentResultsCache[0];
  if (!sample) {
    toast("No sample row to copy", "warning");
    return false;
  }

  const text = JSON.stringify(sample, null, 2);
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text);
    } else {
      const t = document.createElement("textarea");
      t.value = text;
      t.style.position = "fixed";
      t.style.left = "-9999px";
      document.body.appendChild(t);
      t.select();
      document.execCommand("copy");
      t.remove();
    }
    toast("Copied sample row", "success");
    return true;
  } catch {
    toast("Copy failed", "error");
    return false;
  }
}

// ─── Re-clean ───

export async function recleanCurrentJob() {
  if (!currentJobId) return;
  const id = currentJobId;

  showConfirm("AI Re-clean?", "Run AI re-clean on this dataset without re-scraping URLs?", async () => {
    const btn = document.getElementById("btn-reclean");
    const prev = btn ? btn.innerHTML : "";
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<span class="spinner"></span> Re-cleaning...';
    }

    try {
      const res = await apiFetch(endpoints.recleanJob(id), { method: "POST" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Re-clean failed");

      toast(`Re-cleaned rows: ${data.before_records || 0} -> ${data.after_records || 0}`, "success");
      await viewResults(id);
      await refreshJobs();
    } catch (err) {
      toast(`Re-clean error: ${err.message}`, "error");
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = prev || "AI Re-clean";
      }
    }
  });
}

// ─── Export ───

async function downloadExport(url, filename) {
  try {
    const res = await apiFetch(url);
    if (!res.ok) {
      toast("Export failed", "error");
      return;
    }
    const blob = await res.blob();
    const dlUrl = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = dlUrl;
    a.download = filename;
    a.click();
    setTimeout(() => URL.revokeObjectURL(dlUrl), 5000);
  } catch (e) {
    toast(`Export error: ${e.message}`, "error");
  }
}

export async function exportCSV() {
  if (!currentJobId) return;
  await downloadExport(getExportUrl("csv", currentJobId), `job-${currentJobId}.csv`);
}

export async function exportJSON() {
  if (!currentJobId) return;
  await downloadExport(getExportUrl("json", currentJobId), `job-${currentJobId}.json`);
}

export async function exportExcel() {
  if (!currentJobId) return;
  await downloadExport(getExportUrl("excel", currentJobId), `job-${currentJobId}.xlsx`);
}
