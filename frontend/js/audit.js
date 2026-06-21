/* ═══════════════════════════════════
   DataForge — Audit log view
   ═══════════════════════════════════ */

import { apiFetch } from "./api.js";

function escapeHtml(s) {
  return String(s ?? "").replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );
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

function getFilters() {
  const catEl = document.getElementById("audit-category-filter");
  const limitEl = document.getElementById("audit-limit-filter");
  return {
    category: catEl ? catEl.value : "",
    limit: limitEl ? parseInt(limitEl.value, 10) || 100 : 100,
  };
}

function renderEmpty(msg) {
  const list = document.getElementById("audit-list");
  if (!list) return;
  list.innerHTML = `<p class="subtle">${escapeHtml(msg)}</p>`;
}

function renderEvents(events) {
  const list = document.getElementById("audit-list");
  if (!list) return;
  if (!events || events.length === 0) {
    renderEmpty("No audit events found for the current filter.");
    return;
  }
  const tbl = document.createElement("table");
  tbl.className = "audit-table";
  tbl.innerHTML = `
    <thead>
      <tr>
        <th>Time</th>
        <th>Category</th>
        <th>Outcome</th>
        <th>Subject</th>
        <th>Detail</th>
      </tr>
    </thead>
    <tbody></tbody>
  `;
  const tbody = tbl.querySelector("tbody");
  for (const e of events) {
    const tr = document.createElement("tr");
    const time = formatTime(e.timestamp || e.ts);
    const cat = String(e.category || "");
    const outcome = String(e.outcome || "");
    const subject = String(e.subject || e.user_id || e.actor || "");
    const detail = e.detail || e.message || (e.payload ? JSON.stringify(e.payload) : "");
    tr.appendChild(tdCell(time));
    tr.appendChild(tdCell(cat));
    tr.appendChild(tdCellWithClass(outcome, `audit-outcome audit-outcome-${outcome.toLowerCase()}`));
    tr.appendChild(tdCell(subject));
    tr.appendChild(tdCell(typeof detail === "object" ? JSON.stringify(detail) : String(detail)));
    tbody.appendChild(tr);
  }
  list.innerHTML = "";
  list.appendChild(tbl);
}

function tdCell(text) {
  const td = document.createElement("td");
  td.textContent = text;
  return td;
}

function tdCellWithClass(text, cls) {
  const td = document.createElement("td");
  td.className = cls;
  td.textContent = text;
  return td;
}

export async function refreshAudit() {
  const filters = getFilters();
  const params = new URLSearchParams();
  params.set("limit", String(filters.limit));
  if (filters.category) params.set("category", filters.category);
  try {
    const resp = await apiFetch(`/api/system/audit-log?${params.toString()}`);
    if (resp.status === 403) {
      renderEmpty("Audit log is admin-only. You do not have permission to view it.");
      return;
    }
    if (!resp.ok) {
      renderEmpty(`Failed to load audit log: HTTP ${resp.status}`);
      return;
    }
    const body = await resp.json();
    renderEvents(body.items || []);
  } catch (err) {
    renderEmpty(`Failed to load audit log: ${err.message || err}`);
  }
}
