/* ═══════════════════════════════════════════
   DataForge — Data Cleaning Assistant
   ═══════════════════════════════════════════
   Detects field types, previews cleaning
   changes, and applies them to results. */

import { esc, toast } from "./utils.js";

let _cleaningState = null;

// ─── Field Type Detection ────────────────────────────────────────────────
// Priority order (lower = detected first):
// 1. email  (strict format)
// 2. url    (http/https prefix)
// 3. phone  (7+ digits/symbols)
// 4. date   (digit-separator-digit pattern — before number to avoid overlap)
// 5. number (plain digits, optional decimal)
// 6. price  (currency symbols OR explicit decimal with 2 places)

const TYPE_PATTERNS = [
  { type: "email", pattern: /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/, priority: 1 },
  { type: "url", pattern: /^https?:\/\/\S+$/i, priority: 2 },
  { type: "phone", pattern: /^[\d\s\-+()]{7,}$/, priority: 3 },
  { type: "date", pattern: /^\d{1,4}[/\-.]\d{1,2}[/\-.]\d{1,4}$/, priority: 4 },
  { type: "number", pattern: /^-?\d+(\.\d+)?$/, priority: 5 },
  { type: "price", pattern: /^[$€£¥]/, priority: 6 },
];

/**
 * Detect the most likely field type for a column of values.
 * Returns 'text' when no specific pattern matches >50% of non-empty values.
 */
export function detectFieldType(values) {
  if (!Array.isArray(values) || values.length === 0) return "text";
  const nonEmpty = values.filter((v) => v !== null && v !== undefined && v !== "" && v !== "—");
  if (nonEmpty.length === 0) return "text";

  const matched = TYPE_PATTERNS.map((tp) => {
    // Trim values before matching so leading/trailing whitespace doesn't hide type
    const count = nonEmpty.filter((v) => tp.pattern.test(String(v).trim())).length;
    return { type: tp.type, ratio: count / nonEmpty.length, priority: tp.priority };
  })
    .filter((m) => m.ratio > 0.5)
    .sort((a, b) => a.priority - b.priority);

  return matched.length > 0 ? matched[0].type : "text";
}

// ─── Cleaning Rules ──────────────────────────────────────────────────────

function _cleanEmail(v) {
  return String(v).trim().toLowerCase();
}

function _cleanUrl(v) {
  const url = String(v).trim();
  const tracking = /(utm_source|utm_medium|utm_campaign|utm_term|utm_content|fbclid|gclid)=[^&]+/gi;
  return url
    .replace(tracking, "")
    .replace(/[?&]+$/, "")
    .replace(/\?&/, "?");
}

function _cleanPhone(v) {
  return String(v).replace(/\D/g, "");
}

function _cleanPrice(v) {
  const cleaned = String(v).replace(/[$€£¥,\s]/g, "");
  const num = parseFloat(cleaned);
  return isNaN(num) ? v : num;
}

function _cleanNumber(v) {
  const cleaned = String(v).trim().replace(/[,\s]/g, "");
  const num = parseFloat(cleaned);
  return isNaN(num) ? v : num;
}

function _cleanDate(v) {
  const s = String(v).trim();
  const m = s.match(/^(\d{1,4})[/\-.](\d{1,2})[/\-.](\d{1,4})$/);
  if (m) {
    let a = m[1],
      b = m[2],
      c = m[3];
    // Determine order: if one part is 4-digit, it's the year
    if (a.length === 4) {
      // YYYY-MM-DD or YYYY-DD-MM — treat b as month, c as day
      return `${a}-${b.padStart(2, "0")}-${c.padStart(2, "0")}`;
    }
    if (c.length === 4) {
      // MM-DD-YYYY or DD-MM-YYYY — if b > 12 it's day, else treat b as month, c as year
      const bn = parseInt(b, 10);
      const an = parseInt(a, 10);
      if (bn > 12) {
        // b must be day → a is month
        return `${c}-${a.padStart(2, "0")}-${b.padStart(2, "0")}`;
      }
      if (an > 12) {
        // a must be day → b is month
        return `${c}-${b.padStart(2, "0")}-${a.padStart(2, "0")}`;
      }
      // Ambiguous — treat as MM-DD-YYYY (US convention)
      return `${c}-${a.padStart(2, "0")}-${b.padStart(2, "0")}`;
    }
    // No 4-digit part — use as-is with padding
    return `${a.padStart(2, "0")}-${b.padStart(2, "0")}-${c.padStart(2, "0")}`;
  }
  return s;
}

function _cleanText(v) {
  return String(v).trim().replace(/\s+/g, " ");
}

const CLEANERS = {
  email: _cleanEmail,
  url: _cleanUrl,
  phone: _cleanPhone,
  price: _cleanPrice,
  number: _cleanNumber,
  date: _cleanDate,
  text: _cleanText,
};

/**
 * Apply cleaning to a single value given its detected type.
 */
export function cleanValue(value, fieldType) {
  if (value === null || value === undefined || value === "" || value === "—") return value;
  const cleaner = CLEANERS[fieldType] || CLEANERS.text;
  try {
    return cleaner(value);
  } catch {
    return value;
  }
}

/**
 * Check if a value would change after cleaning.
 */
export function wouldChange(value, fieldType) {
  const cleaned = cleanValue(value, fieldType);
  return String(cleaned) !== String(value);
}

// ─── Analyze Rows ────────────────────────────────────────────────────────

/**
 * Analyze results rows to detect field types and compute cleaning stats.
 *
 * @param {Array} rows - Array of result row objects
 * @returns {{ fields: Array, totalChanges: number, totalRows: number }|null}
 */
export function analyzeRows(rows) {
  if (!Array.isArray(rows) || rows.length === 0) {
    _cleaningState = null;
    return null;
  }

  const keys = Object.keys(rows[0] || {}).filter((k) => !k.startsWith("_"));

  const fields = keys.map((key) => {
    const values = rows.map((r) => r[key]);
    const type = detectFieldType(values);
    const nonEmpty = values.filter((v) => v !== null && v !== undefined && v !== "" && v !== "—").length;
    const changeCount = values.filter((v) => wouldChange(v, type)).length;

    let samples = null;
    for (const v of values) {
      if (wouldChange(v, type)) {
        samples = { original: v, cleaned: cleanValue(v, type) };
        break;
      }
    }

    return { name: key, type, nonEmpty, wouldChange: changeCount, samples };
  });

  const totalChanges = fields.reduce((sum, f) => sum + f.wouldChange, 0);

  _cleaningState = { fields, totalChanges, totalRows: rows.length };
  return _cleaningState;
}

export function getCleaningState() {
  return _cleaningState;
}
export function clearCleaningState() {
  _cleaningState = null;
}

// ─── Apply Cleaning ──────────────────────────────────────────────────────

/**
 * Apply cleaning to all rows and return the cleaned dataset.
 * Does NOT modify the results cache — returns cleaned rows.
 */
export function applyCleaning(rows) {
  if (!_cleaningState || !Array.isArray(rows)) return rows;
  const fieldMap = {};
  for (const f of _cleaningState.fields) {
    fieldMap[f.name] = f.type;
  }
  return rows.map((row) => {
    const cleaned = { ...row };
    for (const [key, type] of Object.entries(fieldMap)) {
      if (key in cleaned) {
        cleaned[key] = cleanValue(cleaned[key], type);
      }
    }
    return cleaned;
  });
}

// ─── UI: Summary Panel ───────────────────────────────────────────────────

/**
 * Render cleaning analysis panel in the results view.
 */
export function renderCleaningPanel() {
  const panel = document.getElementById("cleaning-panel");
  if (!panel) return;
  if (!_cleaningState || _cleaningState.totalChanges === 0) {
    panel.classList.add("hidden");
    return;
  }
  const s = _cleaningState;
  panel.classList.remove("hidden");
  panel.innerHTML = `
    <div class="cleaning-panel">
      <div class="cleaning-panel-header">
        <span class="cleaning-panel-title">
          <span data-icon="wrench" aria-hidden="true"></span>
          Data Cleaning
        </span>
        <span class="cleaning-panel-count">
          ${s.totalChanges} value${s.totalChanges !== 1 ? "s" : ""} will change across ${s.fields.filter((f) => f.wouldChange > 0).length} field${s.fields.filter((f) => f.wouldChange > 0).length !== 1 ? "s" : ""}
        </span>
      </div>
      <div class="cleaning-panel-body">
        <p class="cleaning-panel-desc">
          Detected field types and preview of changes for ${s.totalRows} rows.
        </p>
        <div class="cleaning-panel-fields">
          ${s.fields
            .filter((f) => f.wouldChange > 0)
            .map(
              (f) => `
            <div class="cleaning-field-row">
              <div class="cleaning-field-info">
                <span class="cleaning-field-name">${esc(f.name)}</span>
                <span class="cleaning-field-type">${esc(f.type)}</span>
                <span class="cleaning-field-count">${f.wouldChange}/${f.nonEmpty} value${f.wouldChange !== 1 ? "s" : ""}</span>
              </div>
              ${
                f.samples
                  ? `
                <div class="cleaning-field-sample">
                  <span class="cleaning-sample-label">Before:</span>
                  <code class="cleaning-sample-old">${esc(String(f.samples.original))}</code>
                </div>
                <div class="cleaning-field-sample">
                  <span class="cleaning-sample-label">After:</span>
                  <code class="cleaning-sample-new">${esc(String(f.samples.cleaned))}</code>
                </div>
              `
                  : ""
              }
            </div>
          `,
            )
            .join("")}
        </div>
        <div class="cleaning-panel-actions">
          <button type="button" class="btn secondary small" data-action="apply-cleaning" id="btn-apply-cleaning">
            Apply ${s.totalChanges} cleaning change${s.totalChanges !== 1 ? "s" : ""}
          </button>
          <button type="button" class="btn ghost small" data-action="hide-cleaning-panel" id="btn-hide-cleaning-panel">
            Hide
          </button>
        </div>
      </div>
    </div>`;
}

// ─── Actions ─────────────────────────────────────────────────────────────

/**
 * Analyze current results for cleaning opportunities.
 */
export async function analyzeCleaning() {
  try {
    const mod = await import("./results.js");
    const cache = mod.currentResultsCache;
    if (!Array.isArray(cache) || cache.length === 0) {
      toast("No results to analyze", "warning");
      return;
    }
    const state = analyzeRows(cache);
    renderCleaningPanel();
    if (!state || state.totalChanges === 0) {
      toast("No cleaning needed — all values look clean", "success");
    } else {
      toast(
        `Found ${state.totalChanges} value${state.totalChanges !== 1 ? "s" : ""} that can be cleaned across ${state.fields.filter((f) => f.wouldChange > 0).length} field${state.fields.filter((f) => f.wouldChange > 0).length !== 1 ? "s" : ""}`,
        "info",
      );
    }
  } catch (e) {
    toast(`Cleaning analysis failed: ${e.message}`, "error");
  }
}

/**
 * Apply cleaning to current results and re-render.
 */
export async function applyCleaningAction() {
  if (!_cleaningState || _cleaningState.totalChanges === 0) {
    toast("No cleaning to apply", "info");
    return;
  }
  const totalChanges = _cleaningState.totalChanges;
  try {
    const mod = await import("./results.js");
    const cache = mod.currentResultsCache;
    if (!Array.isArray(cache) || cache.length === 0) {
      toast("No results loaded", "warning");
      return;
    }
    const cleaned = applyCleaning(cache);
    const changed = cleaned.filter((row, idx) => JSON.stringify(row) !== JSON.stringify(cache[idx])).length;
    mod.replaceResultsCache(cleaned);
    clearCleaningState();
    mod.renderFilteredResults();
    toast(`Cleaned ${changed} row${changed !== 1 ? "s" : ""} (${totalChanges} values fixed)`, "success");
  } catch (e) {
    toast(`Apply cleaning failed: ${e.message}`, "error");
  }
}
