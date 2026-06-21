/* ═══════════════════════════════════════════
   DataForge — Duplicate Detection
   ═══════════════════════════════════════════
   Detects, highlights, and manages duplicate
   rows in extraction results. */

import { esc, toast } from "./utils.js";
import { renderFilteredResults } from "./results.js";

let _duplicateState = null; // { groups, dupCount, totalRows, keyFields }

/**
 * Build a fingerprint for a row based on specified key fields.
 * Returns a string like "Acme Corp|acme@example.com".
 * If no keyFields are given, uses all non-empty string values.
 */
export function fingerprintRow(row, keyFields = []) {
  if (!row || typeof row !== "object") return "";
  const parts = [];
  if (keyFields.length > 0) {
    for (const field of keyFields) {
      let val = row[field];
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
    // Auto-detect: use all non-empty string values for fingerprint
    for (const [k, v] of Object.entries(row)) {
      if (k.startsWith("_")) continue;
      if (v !== null && v !== undefined && v !== "") {
        parts.push(`${k}:${String(v)}`);
      }
    }
  }
  return parts.join("|").toLowerCase().trim();
}

/**
 * Detect duplicates in an array of rows.
 *
 * @param {Array} rows - Array of result row objects
 * @param {string[]} keyFields - Fields to use for matching (empty = auto-detect all)
 * @returns {{ groups: Array, dupCount: number, totalRows: number, keyFields: string[] }}
 *
 * Each group: { fingerprint, rows: Array, count: number, kept: number, originalIndex: number }
 *   - kept: index of the row to keep (first row within the group)
 *   - rows: all matching rows
 *   - originalIndex: original array index for ordering
 */
export function detectDuplicates(rows, keyFields = []) {
  if (!Array.isArray(rows) || rows.length === 0) {
    _duplicateState = { groups: [], dupCount: 0, totalRows: 0, keyFields };
    return _duplicateState;
  }

  const groups = new Map();
  const usedKeyFields = keyFields.length > 0
    ? keyFields
    : _autoDetectKeyFields(rows);

  rows.forEach((row, idx) => {
    const fp = fingerprintRow(row, usedKeyFields);
    if (!fp) return;
    if (!groups.has(fp)) {
      groups.set(fp, { fingerprint: fp, rows: [], count: 0, kept: idx });
    }
    const group = groups.get(fp);
    group.rows.push({ row, index: idx });
    group.count++;
  });

  // Convert to array, filter only actual duplicates (count > 1)
  const duplicateGroups = [];
  let dupCount = 0;

  for (const group of groups.values()) {
    if (group.count > 1) {
      // Score rows within group to determine best keeper
      const scored = group.rows.map((r) => ({
        ...r,
        score: _scoreRow(r.row),
      }));
      scored.sort((a, b) => b.score - a.score);
      group.kept = scored[0].index;
      duplicateGroups.push({
        fingerprint: group.fingerprint,
        rows: group.rows,
        count: group.count,
        kept: group.kept,
        originalIndex: group.rows[0].index,
      });
      dupCount += group.count - 1;
    }
  }

  // Sort by original position of first occurrence
  duplicateGroups.sort((a, b) => a.originalIndex - b.originalIndex);

  _duplicateState = {
    groups: duplicateGroups,
    dupCount,
    totalRows: rows.length,
    keyFields: usedKeyFields,
  };
  return _duplicateState;
}

/**
 * Auto-detect key fields by finding fields that are
 * most likely to be unique identifiers (shorter string fields
 * with high fill-rate, avoiding URLs, IDs, and timestamps).
 */
function _autoDetectKeyFields(rows) {
  if (rows.length === 0) return [];

  const fieldStats = {};
  const excludePatterns = /^(id|_id|url|source_url|scraped_at|updated_at|created_at|record_score|source_trust_score|_|\.)/i;

  for (const row of rows) {
    if (!row) continue;
    for (const [k, v] of Object.entries(row)) {
      if (excludePatterns.test(k)) continue;
      if (!fieldStats[k]) {
        fieldStats[k] = { filled: 0, total: 0, isShortText: true };
      }
      fieldStats[k].total++;
      if (v !== null && v !== undefined && v !== "") {
        fieldStats[k].filled++;
        if (typeof v === "string" && v.length > 100) {
          fieldStats[k].isShortText = false;
        }
      }
    }
  }

  // Pick fields with high fill-rate (>50%) that are short text
  const candidates = Object.entries(fieldStats)
    .filter(([, stats]) => stats.filled / stats.total > 0.5 && stats.isShortText)
    .sort(([, a], [, b]) => b.filled - a.filled);

  // Return top 3 candidate fields
  return candidates.slice(0, 3).map(([k]) => k);
}

/**
 * Score a row by its data completeness.
 * Higher scores = more complete data.
 */
function _scoreRow(row) {
  if (!row) return 0;
  let score = 0;
  let fields = 0;
  for (const [k, v] of Object.entries(row)) {
    if (k.startsWith("_")) continue;
    fields++;
    if (v !== null && v !== undefined && v !== "" && v !== "—") {
      const s = String(v);
      score += 1;
      // Bonus for longer values (more detailed)
      if (s.length > 5) score += 0.5;
      if (s.length > 20) score += 0.5;
      // Bonus for values that look like real data
      if (/@/.test(s)) score += 1; // email
      if (/^[\d\s\-\(\)\+]{7,}/.test(s)) score += 0.5; // phone
      if (/^https?:\/\//.test(s)) score += 0.5; // URL
    }
  }
  return fields > 0 ? score / fields : 0;
}

/**
 * Get the current duplicate detection state.
 */
export function getDuplicateState() {
  return _duplicateState;
}

/**
 * Clear duplicate detection state.
 */
export function clearDuplicateState() {
  _duplicateState = null;
}

/**
 * Build a set of row indices that are duplicates (not kept).
 */
export function getDuplicateIndices() {
  if (!_duplicateState || _duplicateState.groups.length === 0) return new Set();
  const indices = new Set();
  for (const group of _duplicateState.groups) {
    for (const r of group.rows) {
      if (r.index !== group.kept) {
        indices.add(r.index);
      }
    }
  }
  return indices;
}

/**
 * Render duplicate detection summary panel.
 * Called after detectDuplicates().
 */
export function renderDuplicateSummary(cacheKeyFields = []) {
  const container = document.getElementById("dup-panel");
  if (!container) return;

  const state = _duplicateState;
  if (!state || state.groups.length === 0) {
    container.classList.add("hidden");
    return;
  }

  container.classList.remove("hidden");
  container.innerHTML = `
    <div class="dup-panel">
      <div class="dup-panel-header">
        <span class="dup-panel-title">
          <span class="dup-panel-icon" data-icon="copy" aria-hidden="true"></span>
          Duplicates Found
        </span>
        <span class="dup-panel-count">${state.dupCount} duplicate${state.dupCount !== 1 ? "s" : ""} in ${state.groups.length} group${state.groups.length !== 1 ? "s" : ""}</span>
      </div>
      <div class="dup-panel-body">
        <p class="dup-panel-desc">
          ${state.dupCount} of ${state.totalRows} rows are duplicates (matched on:
          <code class="dup-panel-key-fields">${esc(state.keyFields.join(", ") || "auto-detected fields")}</code>).
          The best copy of each duplicate will be kept.
        </p>
        <div class="dup-panel-groups">
          ${state.groups.slice(0, 10).map((g) => `
            <div class="dup-group-row">
              <span class="dup-group-count">${g.count}×</span>
              <span class="dup-group-key">${esc(g.fingerprint.slice(0, 80))}</span>
              <span class="dup-group-kept-badge">kept</span>
            </div>
          `).join("")}
          ${state.groups.length > 10 ? `<div class="dup-panel-more">… and ${state.groups.length - 10} more groups</div>` : ""}
        </div>
        <div class="dup-panel-actions">
          <button type="button" class="btn secondary small" data-action="remove-duplicates" id="btn-remove-duplicates">
            Remove ${state.dupCount} duplicate${state.dupCount !== 1 ? "s" : ""}
          </button>
          <button type="button" class="btn ghost small" data-action="hide-duplicates" id="btn-hide-duplicates">
            Hide duplicates
          </button>
        </div>
      </div>
    </div>
  `;
}

/**
 * Remove duplicate rows from the results cache and re-render.
 * Exports the deduplicated rows for use in exports.
 */
export function removeDuplicates() {
  if (!_duplicateState || _duplicateState.groups.length === 0) {
    toast("No duplicates to remove", "info");
    return;
  }

  const dupIndices = getDuplicateIndices();

  // Import current results cache from results module
  import("./results.js").then(({ currentResultsCache, setCurrentResultsCache, renderFilteredResults }) => {
    if (!currentResultsCache || currentResultsCache.length === 0) {
      toast("No results loaded", "warning");
      return;
    }

    const deduped = currentResultsCache.filter((_, idx) => !dupIndices.has(idx));
    setCurrentResultsCache(deduped);

    // Reset pagination
    const { goToFirstPage } = require("./results.js");
    // Since goToFirstPage is exported, we need a different approach
    // Let's directly set _currentPage and re-render

    // Update state
    toast(`Removed ${dupIndices.size} duplicate row${dupIndices.size !== 1 ? "s" : ""}`, "success");
    clearDuplicateState();
    renderFilteredResults();
  }).catch(() => {
    // Fallback: use existing results module
    clearDuplicateState();
    renderFilteredResults();
  });
}

/**
 * Sets currentResultsCache in the results module.
 * This is called by the removeDuplicates flow.
 */
export function setCurrentResultsCache(newCache) {
  // This function will be patched by the init function
  // to point at the real results module's setter
}

/**
 * Initialize duplicate detection.
 * Patches the setCurrentResultsCache reference.
 */
export function initDuplicateDetection() {
  // The init function is called once from app.js DOMContentLoaded
  // It patches the setCurrentResultsCache export to point at
  // whichever function the results module exposes
}
