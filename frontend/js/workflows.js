/* ═══════════════════════════════════
   DataForge — Workflows view + run history + preview
   ═══════════════════════════════════ */

import { apiFetch, endpoints } from "./api.js";
import { showConfirm, toast } from "./utils.js";

const RUN_STATUS_BADGE = {
  queued: { label: "Queued", cls: "badge-pending" },
  running: { label: "Running", cls: "badge-running" },
  succeeded: { label: "Succeeded", cls: "badge-success" },
  failed: { label: "Failed", cls: "badge-failed" },
  canceled: { label: "Canceled", cls: "badge-canceled" },
};

const PREVIEW_STATUS_BADGE = {
  succeeded: { label: "Succeeded", cls: "badge-success" },
  failed: { label: "Failed", cls: "badge-failed" },
  partial: { label: "Partial", cls: "badge-running" },
};

let selectedWorkflowId = null;
let runsCache = new Map(); // workflow_id -> {items, fetched_at}

// Round-6 fix: request-token for loadWorkflowDetail so a slow in-flight
// detail load (or a poller-triggered refresh) can't overwrite the pane
// for a different workflow the user just clicked. Each call increments
// the token; the DOM write only commits if the token still matches.
let _loadDetailToken = 0;

export async function refreshWorkflows() {
  const list = document.getElementById("workflows-list");
  const empty = document.getElementById("workflows-empty-state");
  if (!list) return;
  list.innerHTML = "";
  try {
    const resp = await apiFetch("/api/workflows");
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    const items = Array.isArray(data?.items) ? data.items : [];
    if (items.length === 0) {
      if (empty) empty.style.display = "block";
      list.appendChild(empty || document.createTextNode(""));
    } else {
      if (empty) empty.style.display = "none";
      for (const wf of items) {
        list.appendChild(renderWorkflowCard(wf));
      }
    }
    // Update KPI row with a quick tally across all workflows.
    await refreshWorkflowKpis(items);
    // If a workflow was previously selected, refresh its detail pane.
    if (selectedWorkflowId && items.some((w) => w.id === selectedWorkflowId)) {
      await loadWorkflowDetail(selectedWorkflowId);
    } else if (items.length > 0) {
      selectedWorkflowId = items[0].id;
      await loadWorkflowDetail(selectedWorkflowId);
    } else {
      selectedWorkflowId = null;
      const pane = document.getElementById("workflows-detail-pane");
      if (pane) {
        pane.innerHTML =
          '<div class="empty-state-illustration"><p>Select a workflow to see its details and run history.</p></div>';
      }
    }
  } catch (err) {
    list.innerHTML = `<div class="error">Failed to load workflows: ${escapeHtml(String(err))}</div>`;
  }
}

async function refreshWorkflowKpis(items) {
  const setText = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.textContent = String(val);
  };
  setText("workflows-kpi-total", items.length);
  // Lazy-fetch per-workflow run stats to keep the first paint fast.
  let totalRuns = 0;
  let succeeded = 0;
  let failed = 0;
  // Aggregate only workflows that have already loaded runs (capped).
  for (const wf of items) {
    const runs = runsCache.get(wf.id);
    if (!runs) continue;
    totalRuns += runs.items.length;
    for (const r of runs.items) {
      if (r.status === "succeeded") succeeded += 1;
      if (r.status === "failed") failed += 1;
    }
  }
  setText("workflows-kpi-runs", totalRuns);
  setText("workflows-kpi-ok", succeeded);
  setText("workflows-kpi-fail", failed);
}

function renderWorkflowCard(wf) {
  const card = document.createElement("div");
  card.className = "card workflow-card" + (wf.id === selectedWorkflowId ? " selected" : "");
  card.setAttribute("data-id", wf.id);
  card.setAttribute("data-action", "select-workflow");
  card.setAttribute("role", "button");
  card.setAttribute("tabindex", "0");

  const name = document.createElement("div");
  name.className = "workflow-card-name";
  name.textContent = wf.name || "(unnamed)";
  card.appendChild(name);

  const meta = document.createElement("div");
  meta.className = "workflow-card-meta subtle";
  const lastRun = wf.last_run_at ? `Last run: ${formatTime(wf.last_run_at)}` : "Never run";
  meta.textContent = `${wf.total_runs || 0} run(s) — ${lastRun}`;
  card.appendChild(meta);

  if (wf.start_url) {
    const url = document.createElement("div");
    url.className = "workflow-card-url subtle";
    url.textContent = wf.start_url;
    card.appendChild(url);
  }

  card.addEventListener("click", () => {
    selectedWorkflowId = wf.id;
    document.querySelectorAll(".workflow-card").forEach((c) => c.classList.remove("selected"));
    card.classList.add("selected");
    loadWorkflowDetail(wf.id);
  });
  card.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      card.click();
    }
  });
  return card;
}

async function loadWorkflowDetail(workflowId) {
  const pane = document.getElementById("workflows-detail-pane");
  if (!pane) return;
  const myToken = ++_loadDetailToken;
  pane.innerHTML = '<div class="loading">Loading workflow…</div>';
  try {
    const [wfResp, runsResp] = await Promise.all([
      apiFetch(`/api/workflows/${workflowId}`),
      apiFetch(`/api/workflows/${workflowId}/runs?limit=50`),
    ]);
    if (!wfResp.ok) throw new Error(`Workflow fetch failed: HTTP ${wfResp.status}`);
    const wf = await wfResp.json();
    let runs = { items: [], total: 0 };
    if (runsResp.ok) {
      runs = await runsResp.json();
      runsCache.set(workflowId, runs);
    }
    // A newer detail-load has started (user clicked a different workflow,
    // or the poller woke) — drop our stale payload silently.
    if (myToken !== _loadDetailToken) return;
    renderWorkflowDetail(wf, runs);
  } catch (err) {
    if (myToken !== _loadDetailToken) return;
    pane.innerHTML = `<div class="error">Failed to load workflow: ${escapeHtml(String(err))}</div>`;
  }
}

function renderWorkflowDetail(wf, runs) {
  const pane = document.getElementById("workflows-detail-pane");
  if (!pane) return;
  pane.innerHTML = "";

  const head = document.createElement("div");
  head.className = "workflow-detail-head";
  const title = document.createElement("h2");
  title.textContent = wf.name || "(unnamed)";
  head.appendChild(title);
  if (wf.description) {
    const desc = document.createElement("p");
    desc.className = "subtle";
    desc.textContent = wf.description;
    head.appendChild(desc);
  }
  if (wf.start_url) {
    const url = document.createElement("p");
    url.className = "subtle";
    const a = document.createElement("a");
    a.href = wf.start_url;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.textContent = wf.start_url;
    url.appendChild(document.createTextNode("Start: "));
    url.appendChild(a);
    head.appendChild(url);
  }
  const actions = document.createElement("div");
  actions.className = "workflow-detail-actions";
  const runBtn = document.createElement("button");
  runBtn.type = "button";
  runBtn.className = "btn primary";
  runBtn.setAttribute("data-action", "run-workflow");
  runBtn.setAttribute("data-id", wf.id);
  runBtn.textContent = "Run now";
  actions.appendChild(runBtn);
  const previewBtn = document.createElement("button");
  previewBtn.type = "button";
  previewBtn.className = "btn secondary";
  previewBtn.setAttribute("data-action", "preview-workflow");
  previewBtn.setAttribute("data-id", wf.id);
  previewBtn.textContent = "Preview";
  actions.appendChild(previewBtn);
  const delBtn = document.createElement("button");
  delBtn.type = "button";
  delBtn.className = "btn ghost small";
  delBtn.setAttribute("data-action", "delete-workflow");
  delBtn.setAttribute("data-id", wf.id);
  delBtn.textContent = "Delete";
  actions.appendChild(delBtn);
  head.appendChild(actions);
  pane.appendChild(head);

  const stats = document.createElement("div");
  stats.className = "workflow-detail-stats";
  stats.appendChild(statBox("Total runs", wf.total_runs || 0));
  stats.appendChild(statBox("Last run", wf.last_run_at ? formatTime(wf.last_run_at) : "Never"));
  stats.appendChild(statBox("Status", wf.status || "draft"));
  pane.appendChild(stats);

  const runsHeader = document.createElement("div");
  runsHeader.className = "workflow-runs-header";
  const rh = document.createElement("h3");
  rh.textContent = `Run history (${runs.total || 0})`;
  runsHeader.appendChild(rh);
  pane.appendChild(runsHeader);

  if (!runs.items || runs.items.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-state-illustration";
    empty.innerHTML = "<p>No runs yet. Click <strong>Run now</strong> to queue one.</p>";
    pane.appendChild(empty);
    return;
  }

  const tbl = document.createElement("table");
  tbl.className = "runs-table";
  tbl.innerHTML = `
    <thead>
      <tr>
        <th>Status</th>
        <th>Queued</th>
        <th>Started</th>
        <th>Finished</th>
        <th>Job</th>
      </tr>
    </thead>
    <tbody></tbody>
  `;
  const tbody = tbl.querySelector("tbody");
  for (const r of runs.items) {
    const row = document.createElement("tr");
    row.appendChild(badgeCell(r.status));
    row.appendChild(tdCell(formatTime(r.queued_at)));
    row.appendChild(tdCell(r.started_at ? formatTime(r.started_at) : "—"));
    row.appendChild(tdCell(r.finished_at ? formatTime(r.finished_at) : "—"));
    row.appendChild(tdCell(r.job_id || "—"));
    tbody.appendChild(row);
  }
  pane.appendChild(tbl);
}

function statBox(label, value) {
  const div = document.createElement("div");
  div.className = "workflow-stat";
  const l = document.createElement("div");
  l.className = "workflow-stat-label";
  l.textContent = label;
  const v = document.createElement("div");
  v.className = "workflow-stat-value";
  v.textContent = String(value);
  div.appendChild(l);
  div.appendChild(v);
  return div;
}

function badgeCell(status) {
  const td = document.createElement("td");
  const span = document.createElement("span");
  const meta = RUN_STATUS_BADGE[status] || { label: status || "unknown", cls: "badge-unknown" };
  span.className = `badge ${meta.cls}`;
  span.textContent = meta.label;
  td.appendChild(span);
  return td;
}

function tdCell(text) {
  const td = document.createElement("td");
  td.textContent = text;
  return td;
}

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

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

export async function onWorkflowAction(action, id) {
  if (action === "run-workflow" && id) {
    try {
      const resp = await apiFetch(`/api/workflows/${id}/run`, { method: "POST" });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      toast(`Workflow queued (job ${data.job_id || "—"})`, "success");
      await loadWorkflowDetail(id);
    } catch (err) {
      toast(`Failed to queue workflow: ${err.message || err}`, "error");
    }
  }
  if (action === "preview-workflow" && id) {
    await previewWorkflow(id);
  }
  if (action === "delete-workflow" && id) {
    showConfirm("Delete Workflow?", "Delete this workflow? This cannot be undone.", async () => {
      try {
        const resp = await apiFetch(`/api/workflows/${id}`, { method: "DELETE" });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        selectedWorkflowId = null;
        runsCache.delete(id);
        await refreshWorkflows();
      } catch (err) {
        toast(`Failed to delete workflow: ${err.message || err}`, "error");
      }
    });
  }
}

// ── Preview ──────────────────────────────────────────────────────────────

async function previewWorkflow(workflowId) {
  let previewContainer = document.getElementById("workflow-preview-results");
  if (!previewContainer) {
    const pane = document.getElementById("workflows-detail-pane");
    if (!pane) return;
    previewContainer = document.createElement("div");
    previewContainer.id = "workflow-preview-results";
    previewContainer.className = "workflow-preview-section";
    pane.appendChild(previewContainer);
  }

  // Show loading state
  previewContainer.innerHTML = '<div class="loading">Previewing workflow…</div>';

  try {
    const url = endpoints.workflowPreview(workflowId);
    const resp = await apiFetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sample_limit: 5 }),
    });
    if (!resp.ok) {
      const errBody = await resp.text().catch(() => "");
      throw new Error(`HTTP ${resp.status}: ${errBody || "preview failed"}`);
    }
    const result = await resp.json();
    renderPreviewResults(previewContainer, result);
  } catch (err) {
    previewContainer.innerHTML = `<div class="error">Preview failed: ${escapeHtml(String(err.message || err))}</div>`;
  }
}

function renderPreviewResults(container, result) {
  container.innerHTML = "";

  const header = document.createElement("div");
  header.className = "workflow-preview-header";

  const title = document.createElement("h4");
  title.textContent = "Preview Results";

  const statusMeta = PREVIEW_STATUS_BADGE[result.preview_status] || {
    label: result.preview_status || "unknown",
    cls: "badge-unknown",
  };
  const statusBadge = document.createElement("span");
  statusBadge.className = `badge ${statusMeta.cls}`;
  statusBadge.textContent = statusMeta.label;
  header.appendChild(title);
  header.appendChild(statusBadge);
  container.appendChild(header);

  if (result.preview_status === "succeeded" && result.records && result.records.length > 0) {
    // Render extracted records in a compact table
    const tbl = document.createElement("table");
    tbl.className = "preview-table";

    // Build columns from first record keys
    const keys = Object.keys(result.records[0]);
    const thead = document.createElement("thead");
    const headerRow = document.createElement("tr");
    for (const key of keys) {
      const th = document.createElement("th");
      th.textContent = key;
      headerRow.appendChild(th);
    }
    thead.appendChild(headerRow);
    tbl.appendChild(thead);

    const tbody = document.createElement("tbody");
    for (const record of result.records) {
      const row = document.createElement("tr");
      for (const key of keys) {
        const td = document.createElement("td");
        td.textContent = String(record[key] ?? "");
        row.appendChild(td);
      }
      tbody.appendChild(row);
    }
    tbl.appendChild(tbody);
    container.appendChild(tbl);

    // Summary line
    const summary = document.createElement("div");
    summary.className = "subtle preview-summary";
    summary.textContent = `${result.records.length} record(s) extracted`;
    container.appendChild(summary);
  } else if (result.preview_status === "succeeded" && (!result.records || result.records.length === 0)) {
    const empty = document.createElement("div");
    empty.className = "empty-state-illustration";
    empty.innerHTML = "<p>Preview completed but no records were extracted.</p>";
    container.appendChild(empty);
  } else {
    // Failed / partial preview
    const errorDiv = document.createElement("div");
    errorDiv.className = "error";
    const msg = result.user_message || result.failure_type || result.error || "Preview failed with no details";
    errorDiv.textContent = String(msg);
    container.appendChild(errorDiv);
  }
}
