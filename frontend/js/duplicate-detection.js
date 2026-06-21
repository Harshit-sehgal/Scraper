/* ═══════════════════════════════════════════
   DataForge — Duplicate Detection
   ═══════════════════════════════════════════
   Detects, highlights, and manages duplicate
   rows in extraction results. */

import { esc, toast } from "./utils.js";

let _duplicateState = null;

// ─── Fingerprinting ──────────────────────────────────────────────────────

/**
 * Build a fingerprint for a row based on specified key fields.
 * Returns a lowercased string like "acme corp|acme@example.com".
 * Pass empty keyFields to auto-detect from all non-empty, non-meta fields.
 */
export function fingerprintRow(row, keyFields = []) {
  if (!row || typeof row !== "object") return "";
  const parts = [];
  if (keyFields.length > 0) {
    for (const field of keyFields) {
      const val = row[field];
      if (val === null || val === undefined || val === "") {
        parts.push("");
      } else if (typeof val === "object" && !Array.isArray(val)) {
        parts.push(JSON.stringify(val));
      } else if (Array.isArray(val)) {
        parts.push(val.join(", "));
      } else {
        parts.push(String(val));
      }
    }
  } else {
    // Auto-detect: concatenate all non-meta field values
    for (const [k, v] of Object.entries(row)) {
      if (k.startsWith("_")) continue;
      if (v !== null && v !== undefined && v !== "") {
        parts.push(`${k}:${String(v)}`);
      }
    }
  }
  return parts.join("|").toLowerCase().trim();
}

// ─── Auto-detect Key Fields ─────────────────────────────────────────────

function _autoDetectKeyFields(rows) {
  if (rows.length === 0) return [];
  const exclude = /^(id|_id|url|source_url|scraped_at|updated_at|created_at|record_score|source_trust_score|_)/i;
  const stats = {};
  for (const row of rows) {
    if (!row) continue;
    for (const [k, v] of Object.entries(row)) {
      if (exclude.test(k)) continue;
      if (!stats[k]) stats[k] = { filled: 0, total: 0, short: true };
      stats[k].total++;
      if (v !== null && v !== undefined && v !== "") {
        stats[k].filled++;
        if (typeof v === "string" && v.length > 100) stats[k].short = false;
      }
    }
  }
  return Object.entries(stats)
    .filter(([, s]) => s.filled / s.total > 0.5 && s.short)
    .sort(([, a], [, b]) => b.filled - a.filled)
    .slice(0, 3)
    .map(([k]) => k);
}

// ─── Scoring ────────────────────────────────────────────────────────────

function _scoreRow(row) {
  if (!row) return 0;
  let total = 0,
    fields = 0;
  for (const [k, v] of Object.entries(row)) {
    if (k.startsWith("_")) continue;
    fields++;
    if (v !== null && v !== undefined && v !== "" && v !== "—") {
      const s = String(v);
      total += 1;
      if (s.length > 5) total += 0.5;
      if (s.length > 20) total += 0.5;
      if (/@/.test(s)) total += 1;
      if (/^[\d\s\-()]+$/.test(s) && s.length > 6) total += 0.5;
      if (/^https?:\/\//.test(s)) total += 0.5;
    }
  }
  return fields > 0 ? total / fields : 0;
}

// ─── Detection ──────────────────────────────────────────────────────────

/**
 * Detect duplicates in an array of rows.
 *
 * @param {Array} rows - Result row objects
 * @param {string[]} [keyFields] - Fields to match on (empty = auto-detect)
 * @returns {{ groups: Array, dupCount: number, totalRows: number, keyFields: string[] }}
 */
export function detectDuplicates(rows, keyFields = []) {
  if (!Array.isArray(rows) || rows.length === 0) {
    _duplicateState = { groups: [], dupCount: 0, totalRows: 0, keyFields: [] };
    return _duplicateState;
  }

  const used = keyFields.length > 0 ? keyFields : _autoDetectKeyFields(rows);
  const groups = new Map();

  rows.forEach((row, idx) => {
    const fp = fingerprintRow(row, used);
    if (!fp) return;
    if (!groups.has(fp)) {
      groups.set(fp, { fingerprint: fp, rows: [], count: 0, kept: idx });
    }
    const g = groups.get(fp);
    g.rows.push({ row, index: idx });
    g.count++;
  });

  const dups = [];
  let totalDups = 0;
  for (const g of groups.values()) {
    if (g.count > 1) {
      const scored = g.rows.map((r) => ({ ...r, score: _scoreRow(r.row) }));
      scored.sort((a, b) => b.score - a.score);
      g.kept = scored[0].index;
      dups.push({
        fingerprint: g.fingerprint,
        rows: g.rows,
        count: g.count,
        kept: g.kept,
        originalIndex: g.rows[0].index,
      });
      totalDups += g.count - 1;
    }
  }
  dups.sort((a, b) => a.originalIndex - b.originalIndex);

  _duplicateState = { groups: dups, dupCount: totalDups, totalRows: rows.length, keyFields: used };
  return _duplicateState;
}

/**
 * Build a Set of row indices that are duplicates (not the kept copy).
 */
export function getDuplicateIndices() {
  if (!_duplicateState?.groups.length) return new Set();
  const s = new Set();
  for (const g of _duplicateState.groups) {
    for (const r of g.rows) {
      if (r.index !== g.kept) s.add(r.index);
    }
  }
  return s;
}

/**
 * Get current duplicate state.
 */
export function getDuplicateState() {
  return _duplicateState;
}
export function clearDuplicateState() {
  _duplicateState = null;
}

// ─── UI: Summary Panel ──────────────────────────────────────────────────

/**
 * Render the duplicate summary panel below the results table.
 */
export function renderDuplicateSummary() {
  const panel = document.getElementById("dup-panel");
  if (!panel) return;
  if (!_duplicateState || _duplicateState.groups.length === 0) {
    panel.classList.add("hidden");
    return;
  }
  const s = _duplicateState;
  panel.classList.remove("hidden");
  panel.innerHTML = `
    <div class="dup-panel">
      <div class="dup-panel-header">
        <span class="dup-panel-title">
          <span data-icon="copy" aria-hidden="true"></span>
          Duplicates Found
        </span>
        <span class="dup-panel-count">${s.dupCount} duplicate${s.dupCount !== 1 ? "s" : ""} in ${s.groups.length} group${s.groups.length !== 1 ? "s" : ""}</span>
      </div>
      <div class="dup-panel-body">
        <p class="dup-panel-desc">
          ${s.dupCount} of ${s.totalRows} rows matched on
          <code>${esc(s.keyFields.join(", ") || "auto-detected fields")}</code>.
          The most complete copy of each group will be kept.
        </p>
        <div class="dup-panel-groups">
          ${s.groups
            .slice(0, 10)
            .map(
              (g) => `
            <div class="dup-group-row">
              <span class="dup-group-count">${g.count}×</span>
              <span class="dup-group-key">${esc(g.fingerprint.slice(0, 80))}</span>
              <span class="dup-group-kept-badge" title="Row kept">kept</span>
            </div>
          `,
            )
            .join("")}
          ${s.groups.length > 10 ? `<div class="dup-panel-more">… and ${s.groups.length - 10} more groups</div>` : ""}
        </div>
        <div class="dup-panel-actions">
          <button type="button" class="btn secondary small" data-action="remove-duplicates" id="btn-remove-duplicates">
            Remove ${s.dupCount} duplicate${s.dupCount !== 1 ? "s" : ""}
          </button>
          <button type="button" class="btn ghost small" data-action="hide-duplicate-panel" id="btn-hide-dup-panel">
            Hide
          </button>
        </div>
      </div>
    </div>`;
}

// ─── Action: Find Duplicates in Current Results ─────────────────────────

/**
 * Find duplicates in the current results cache.
 * Imports results module dynamically to get currentResultsCache.
 */
export async function findDuplicates(keyFields = []) {
  try {
    const mod = await import("./results.js");
    const cache = mod.currentResultsCache;
    if (!Array.isArray(cache) || cache.length === 0) {
      toast("No results to scan", "warning");
      return;
    }
    const state = detectDuplicates(cache, keyFields);
    renderDuplicateSummary();
    if (state.groups.length === 0) {
      toast("No duplicates found — all rows are unique", "success");
    } else {
      toast(
        `Found ${state.dupCount} duplicate${state.dupCount !== 1 ? "s" : ""} in ${state.groups.length} group${state.groups.length !== 1 ? "s" : ""}`,
        "info",
      );
    }
  } catch (e) {
    toast(`Duplicate detection failed: ${e.message}`, "error");
  }
}

// ─── Action: Remove Duplicates ──────────────────────────────────────────

/**
 * Remove duplicate rows from the current results cache and re-render.
 */
export async function removeDuplicates() {
  if (!_duplicateState?.groups.length) {
    toast("No duplicates to remove", "info");
    return;
  }
  const indices = getDuplicateIndices();
  try {
    const mod = await import("./results.js");
    const cache = mod.currentResultsCache;
    if (!Array.isArray(cache) || cache.length === 0) {
      toast("No results loaded", "warning");
      return;
    }
    const deduped = cache.filter((_, idx) => !indices.has(idx));
    mod.replaceResultsCache(deduped);
    clearDuplicateState();
    // Re-render the table directly (goToFirstPage early-returns when on page 1)
    mod.renderFilteredResults();
    toast(`Removed ${indices.size} duplicate row${indices.size !== 1 ? "s" : ""}`, "success");
  } catch (e) {
    toast(`Remove duplicates failed: ${e.message}`, "error");
  }
}

// ─── Init ───────────────────────────────────────────────────────────────

/**
 * Init is a no-op — all actions go through findDuplicates / removeDuplicates.
 */
export function initDuplicateDetection() {
  // DOM bindings are handled by app.js delegated click handler
}
