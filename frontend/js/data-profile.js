/* ═══════════════════════════════════════════
   DataForge — Data Profile Summary
   ═══════════════════════════════════════════
   Generates field-level statistics from
   extraction results: completeness, unique
   values, empty count, type distribution. */

import { esc, toast } from "./utils.js";

let _profileState = null;

// ─── Profile Generation ──────────────────────────────────────────────────

/**
 * Generate a data profile from an array of result rows.
 *
 * @param {Array} rows - Array of result objects
 * @returns {{ fields: Array, totalRows: number, totalFields: number, emptyFields: number }}
 *
 * Each field: { name, nonEmpty, empty, fillRate, uniqueValues, sampleValues }
 */
export function generateProfile(rows) {
  if (!Array.isArray(rows) || rows.length === 0) {
    _profileState = null;
    return null;
  }

  const keys = Object.keys(rows[0] || {}).filter((k) => !k.startsWith("_"));
  let emptyFields = 0;

  const fields = keys.map((key) => {
    const values = rows.map((r) => r[key]);
    const nonEmpty = values.filter((v) => v !== null && v !== undefined && v !== "" && v !== "—").length;
    const empty = rows.length - nonEmpty;

    if (empty === rows.length) emptyFields++;

    // Count unique values (sample up to 100 for perf)
    const uniqueSet = new Set();
    const uniqueTypes = new Set();
    for (const v of values) {
      if (v !== null && v !== undefined && v !== "" && v !== "—") {
        const s = String(v).slice(0, 100);
        uniqueSet.add(s);
        uniqueTypes.add(typeof v === "object" ? "object" : typeof v);
      }
    }

    // Get a few sample values
    const sampleValues = [];
    for (const v of values) {
      if (v !== null && v !== undefined && v !== "" && v !== "—") {
        sampleValues.push(v);
        if (sampleValues.length >= 3) break;
      }
    }

    const fillRate = rows.length > 0 ? Math.round((nonEmpty / rows.length) * 100) : 0;

    return {
      name: key,
      nonEmpty,
      empty,
      fillRate,
      uniqueValues: uniqueSet.size,
      types: [...uniqueTypes].join(", "),
      sampleValues,
    };
  });

  _profileState = { fields, totalRows: rows.length, totalFields: fields.length, emptyFields };
  return _profileState;
}

/**
 * Get current profile state.
 */
export function getProfileState() {
  return _profileState;
}
export function clearProfileState() {
  _profileState = null;
}

// ─── UI: Profile Panel ───────────────────────────────────────────────────

/**
 * Render data profile panel below the results table.
 */
export function renderProfilePanel() {
  const panel = document.getElementById("profile-panel");
  if (!panel) return;
  if (!_profileState) {
    panel.classList.add("hidden");
    return;
  }
  const s = _profileState;
  panel.classList.remove("hidden");

  // Calculate overall stats
  const filledFields = s.fields.filter((f) => f.fillRate > 0);
  const avgFillRate =
    filledFields.length > 0
      ? Math.round(filledFields.reduce((sum, f) => sum + f.fillRate, 0) / filledFields.length)
      : 0;
  const totalUnique = s.fields.reduce((sum, f) => sum + f.uniqueValues, 0);

  panel.innerHTML = `
    <div class="profile-panel">
      <div class="profile-panel-header">
        <span class="profile-panel-title">
          <span data-icon="chartBar" aria-hidden="true"></span>
          Data Profile
        </span>
        <span class="profile-panel-count">
          ${s.totalRows} rows · ${s.totalFields} fields · ${avgFillRate}% avg fill
        </span>
      </div>
      <div class="profile-panel-body">
        <div class="profile-kpi-row">
          <div class="profile-kpi">
            <span class="profile-kpi-val">${s.totalRows}</span>
            <span class="profile-kpi-label">Rows</span>
          </div>
          <div class="profile-kpi">
            <span class="profile-kpi-val">${s.totalFields}</span>
            <span class="profile-kpi-label">Fields</span>
          </div>
          <div class="profile-kpi">
            <span class="profile-kpi-val">${avgFillRate}%</span>
            <span class="profile-kpi-label">Avg fill rate</span>
          </div>
          <div class="profile-kpi">
            <span class="profile-kpi-val">${totalUnique}</span>
            <span class="profile-kpi-label">Unique values</span>
          </div>
          <div class="profile-kpi">
            <span class="profile-kpi-val">${s.emptyFields}</span>
            <span class="profile-kpi-label">Empty fields</span>
          </div>
        </div>
        <div class="profile-fields">
          ${s.fields
            .map((f) => {
              const barClass =
                f.fillRate >= 90
                  ? "profile-bar-high"
                  : f.fillRate >= 50
                    ? "profile-bar-mid"
                    : f.fillRate > 0
                      ? "profile-bar-low"
                      : "profile-bar-empty";
              return `
            <div class="profile-field-row">
              <div class="profile-field-info">
                <span class="profile-field-name">${esc(f.name)}</span>
                <span class="profile-field-meta">
                  ${f.nonEmpty}/${f.totalRows} · ${f.uniqueValues} unique · ${f.types || "—"}
                </span>
              </div>
              <div class="profile-field-bar-track">
                <div class="profile-field-bar-fill ${barClass}"
                  style="width: ${f.fillRate}%"
                  title="${f.fillRate}% fill rate"></div>
              </div>
              <div class="profile-field-pct">${f.fillRate}%</div>
              ${
                f.sampleValues.length > 0
                  ? `
                <div class="profile-field-samples">
                  ${f.sampleValues
                    .map((sv) => `<code class="profile-sample">${esc(String(sv).slice(0, 40))}</code>`)
                    .join("")}
                </div>
              `
                  : `
                <span class="profile-empty-label">all empty</span>
              `
              }
            </div>`;
            })
            .join("")}
        </div>
        <div class="profile-panel-actions">
          <button type="button" class="btn ghost small" data-action="hide-profile-panel" id="btn-hide-profile">
            Close
          </button>
        </div>
      </div>
    </div>`;
}

// ─── Actions ─────────────────────────────────────────────────────────────

/**
 * Generate and show data profile for current results.
 */
export async function showDataProfile() {
  try {
    const mod = await import("./results.js");
    const cache = mod.currentResultsCache;
    if (!Array.isArray(cache) || cache.length === 0) {
      toast("No results to profile", "warning");
      return;
    }
    const profile = generateProfile(cache);
    renderProfilePanel();
    if (profile) {
      toast(`Profile generated: ${profile.totalRows} rows, ${profile.totalFields} fields`, "success");
    }
  } catch (e) {
    toast(`Data profile failed: ${e.message}`, "error");
  }
}
