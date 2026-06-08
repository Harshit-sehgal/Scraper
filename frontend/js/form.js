/* ═══════════════════════════════════════════
   DataForge — Job Form
   ═══════════════════════════════════════════ */

import { esc, attrStr, toast } from "./utils.js";
import { API, apiFetch } from "./api.js";
import { currentMode, setMode } from "./views.js";

// ─── Field Counter ───

let _fieldCounter = 0;
let _filterCounter = 0;

// ─── Init Form ───

export async function initForm() {
  _fieldCounter = 0;
  _filterCounter = 0;
  const setVal = (id, v) => {
    const el = document.getElementById(id);
    if (el) el.value = v;
  };
  const setHtml = (id, v) => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = v;
  };
  setVal("inp-name", "");
  setVal("inp-intent", "");
  setVal("inp-topic", "");
  setVal("inp-location", "");
  setVal("inp-domain", "");
  setVal("inp-origin-location", "");
  setVal("inp-max-distance-km", "");
  setVal("inp-discover-pages", "12");
  setVal("inp-max-per-domain", "4");
  setVal("inp-urls", "");
  setVal("inp-max-pages", "10");
  setVal("inp-min-score", "0.35");
  setVal("inp-source-policy", "official_plus_directory");
  setHtml("schema-container", "");
  setHtml("filters-container", "");
  const preview = document.getElementById("discovery-preview");
  if (preview) {
    preview.innerHTML = "";
    preview.classList.add("hidden");
  }
  const note = document.getElementById("suggestion-note");
  if (note) {
    note.textContent = "";
    note.classList.add("hidden");
  }
  setMode("manual");
  const { clearAnalysis } = await import("./analyzer.js");
  clearAnalysis();
  addField();
}

// ─── Add Schema Field ───

export function addField(preset = null) {
  const c = document.getElementById("schema-container");
  const row = document.createElement("div");
  row.className = "field-row";
  const p = preset || {};
  const name = attrStr(p.name || "");
  const desc = attrStr(p.description || "");
  const selectedType = p.field_type || "string";
  const fid = _fieldCounter++;
  row.innerHTML = `
        <div class="form-group">
            <label for="sf-name-${fid}">Name</label>
            <input type="text" class="sf-name" id="sf-name-${fid}" placeholder="company_name" value="${name}">
        </div>
        <div class="form-group">
            <label for="sf-type-${fid}">Type</label>
            <select class="sf-type" id="sf-type-${fid}">
                <option value="string" ${selectedType === "string" ? "selected" : ""}>Text</option>
                <option value="integer" ${selectedType === "integer" ? "selected" : ""}>Integer</option>
                <option value="float" ${selectedType === "float" ? "selected" : ""}>Decimal</option>
                <option value="boolean" ${selectedType === "boolean" ? "selected" : ""}>Boolean</option>
                <option value="email" ${selectedType === "email" ? "selected" : ""}>Email</option>
                <option value="url" ${selectedType === "url" ? "selected" : ""}>URL</option>
                <option value="phone" ${selectedType === "phone" ? "selected" : ""}>Phone</option>
                <option value="location" ${selectedType === "location" ? "selected" : ""}>Location</option>
                <option value="date" ${selectedType === "date" ? "selected" : ""}>Date</option>
                <option value="list_string" ${selectedType === "list_string" ? "selected" : ""}>List</option>
                <option value="currency" ${selectedType === "currency" ? "selected" : ""}>Currency</option>
                <option value="percentage" ${selectedType === "percentage" ? "selected" : ""}>Percentage</option>
            </select>
        </div>
        <div class="form-group">
            <label for="sf-desc-${fid}">Hint for AI</label>
            <input type="text" class="sf-desc" id="sf-desc-${fid}" placeholder="e.g. star rating out of 5" value="${desc}">
        </div>
        <button type="button" class="btn-x" data-action="remove-field" aria-label="Remove field">✕</button>
    `;
  c.appendChild(row);
}

// ─── Suggest Schema from Intent ───

export async function suggestSchemaFromIntent() {
  const intentEl = document.getElementById("inp-intent");
  const intent = intentEl ? intentEl.value.trim() : "";
  if (!intent) {
    toast("Describe your data goal first", "error");
    return;
  }

  const btn = document.getElementById("btn-suggest-schema");
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Suggesting...';
  }

  try {
    const res = await apiFetch(`${API}/api/schema/suggest`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ intent, max_fields: 8 }),
    });
    if (!res.ok) {
      throw new Error((await res.json().catch(() => ({}))).detail || "Suggestion failed");
    }

    const data = await res.json();
    if (data.topic) document.getElementById("inp-topic").value = data.topic;
    if (data.location) document.getElementById("inp-location").value = data.location;
    if (data.origin_location) document.getElementById("inp-origin-location").value = data.origin_location;
    if (data.max_distance_km !== null && data.max_distance_km !== undefined) {
      document.getElementById("inp-max-distance-km").value = String(data.max_distance_km);
    }

    if (Array.isArray(data.fields) && data.fields.length) {
      const schemaContainer = document.getElementById("schema-container");
      schemaContainer.innerHTML = "";
      data.fields.forEach((f) => addField(f));
    }

    const note = document.getElementById("suggestion-note");
    const notes = (data.notes || "").trim();
    if (notes) {
      note.textContent = notes;
      note.classList.remove("hidden");
    } else {
      note.textContent = "";
      note.classList.add("hidden");
    }

    setMode("auto");
    toast("Schema suggestion applied", "success");
  } catch (err) {
    toast(`Suggestion error: ${err.message}`, "error");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "Suggest topic + schema from intent";
    }
  }
}

// ─── Add Filter ───

export function addFilter() {
  const c = document.getElementById("filters-container");
  const fieldOptions = Array.from(document.querySelectorAll(".sf-name"))
    .map((i) => i.value)
    .filter((v) => v)
    .map((v) => `<option value="${attrStr(v)}">${esc(v)}</option>`)
    .join("");

  const fid = _filterCounter++;
  const row = document.createElement("div");
  row.className = "filter-row";
  row.innerHTML = `
        <div class="form-group">
            <label for="ff-field-${fid}">Field</label>
            <select class="ff-field" id="ff-field-${fid}">${fieldOptions || '<option value="">—</option>'}</select>
        </div>
        <div class="form-group">
            <label for="ff-op-${fid}">Operator</label>
            <select class="ff-op" id="ff-op-${fid}" data-action="filter-op-change">
                <option value="equals">Equals</option>
                <option value="not_equals">Not Equals</option>
                <option value="greater_than">&gt; Greater</option>
                <option value="less_than">&lt; Less</option>
                <option value="greater_equal">≥ Greater/Eq</option>
                <option value="less_equal">≤ Less/Eq</option>
                <option value="contains">Contains</option>
                <option value="not_contains">Not Contains</option>
                <option value="starts_with">Starts With</option>
                <option value="ends_with">Ends With</option>
                <option value="in_list">In List</option>
                <option value="is_empty">Is Empty</option>
                <option value="is_not_empty">Is Not Empty</option>
                <option value="matches_regex">Regex</option>
                <option value="distance_within">Distance Within</option>
            </select>
        </div>
        <div class="form-group ff-value-group">
            <label for="ff-value-${fid}">Value</label>
            <input type="text" class="ff-value" id="ff-value-${fid}" placeholder="e.g. 50">
        </div>
        <button type="button" class="btn-x" data-action="remove-filter" aria-label="Remove field">✕</button>
    `;
  c.appendChild(row);
}

// ─── Filter Operator Change ───

export function onFilterOpChange(sel) {
  const row = sel.closest(".filter-row");
  const isDistance = sel.value === "distance_within";
  row.querySelectorAll(".dist-extra").forEach((el) => el.remove());

  if (isDistance) {
    row.classList.add("has-distance");
    row.querySelector(".ff-value-group label").textContent = "Max km/mi";
    const xBtn = row.querySelector(".btn-x");
    const distId = _filterCounter;
    const origin = document.createElement("div");
    origin.className = "form-group dist-extra";
    origin.innerHTML = `<label for="ff-origin-${distId}">Origin address</label><input type="text" class="ff-origin" id="ff-origin-${distId}" placeholder="Los Angeles, CA">`;
    const unit = document.createElement("div");
    unit.className = "form-group dist-extra";
    unit.innerHTML = `<label for="ff-unit-${distId}">Unit</label><select class="ff-unit" id="ff-unit-${distId}"><option value="km">km</option><option value="miles">miles</option></select>`;
    row.insertBefore(origin, xBtn);
    row.insertBefore(unit, xBtn);
  } else {
    row.classList.remove("has-distance");
    row.querySelector(".ff-value-group label").textContent = "Value";
  }
}

// ─── Preview Discovery ───

export async function previewDiscovery() {
  const topic = document.getElementById("inp-topic").value.trim();
  if (!topic) {
    toast("Enter a topic first", "error");
    return;
  }

  const discoverInput = parseInt(document.getElementById("inp-discover-pages").value, 10);
  const discoverCount = Number.isFinite(discoverInput) ? Math.max(1, Math.min(20, discoverInput)) : 8;
  document.getElementById("inp-discover-pages").value = String(discoverCount);
  const perDomainInput = parseInt(document.getElementById("inp-max-per-domain").value, 10);
  const maxPerDomain = Number.isFinite(perDomainInput) ? Math.max(1, Math.min(25, perDomainInput)) : 4;
  document.getElementById("inp-max-per-domain").value = String(maxPerDomain);

  const preview = document.getElementById("discovery-preview");
  preview.classList.remove("hidden");
  preview.innerHTML = '<div class="disc-loading"><span class="spinner"></span> Discovering URLs...</div>';

  try {
    const res = await apiFetch(`${API}/api/discover`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        topic,
        location: document.getElementById("inp-location").value.trim(),
        domain: document.getElementById("inp-domain").value.trim(),
        num_results: discoverCount,
        max_per_domain: maxPerDomain,
        source_policy: document.getElementById("inp-source-policy").value || "official_plus_directory",
        schema_field_names: Array.from(document.querySelectorAll(".sf-name"))
          .map((i) => i.value.trim())
          .filter(Boolean),
        origin_location: document.getElementById("inp-origin-location").value.trim(),
        max_distance_km: (() => {
          const n = parseFloat(document.getElementById("inp-max-distance-km").value);
          return Number.isFinite(n) ? n : null;
        })(),
      }),
    });

    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "Discovery failed");
    if (!data.urls?.length) {
      preview.innerHTML = '<div class="disc-loading">No URLs found. Try a different topic.</div>';
      return;
    }

    preview.innerHTML = data.urls
      .map(
        (u) => `
            <div class="disc-item">
                <div class="disc-url">${esc(u.url || "")}</div>
                <div class="disc-reason">${esc(u.title || "")} — ${esc(u.reason || "")}</div>
            </div>
        `,
      )
      .join("");
  } catch (e) {
    preview.innerHTML = `<div class="disc-loading">Discovery error: ${esc(e.message || "Unknown error")}</div>`;
  }
}

// ─── Submit Job ───

export async function submitJob(e) {
  e.preventDefault();

  const name = document.getElementById("inp-name").value.trim();
  if (!name) {
    toast("Enter a job name", "error");
    return;
  }

  // Schema
  const schema = [];
  document.querySelectorAll(".field-row").forEach((row) => {
    const n = row.querySelector(".sf-name").value.trim();
    if (n)
      schema.push({
        name: n,
        field_type: row.querySelector(".sf-type").value,
        description: row.querySelector(".sf-desc").value.trim(),
        required: true,
      });
  });
  if (!schema.length) {
    toast("Add at least one schema field", "error");
    return;
  }

  // Filters
  const filters = [];
  document.querySelectorAll(".filter-row").forEach((row) => {
    const f = row.querySelector(".ff-field").value;
    const op = row.querySelector(".ff-op").value;
    const val = row.querySelector(".ff-value")?.value.trim() || "";
    if (f) {
      const filter = { field_name: f, operator: op, value: val };
      if (op === "distance_within") {
        filter.origin_address = row.querySelector(".ff-origin")?.value.trim() || "";
        filter.distance_unit = row.querySelector(".ff-unit")?.value || "km";
      }
      filters.push(filter);
    }
  });

  // URLs or topic
  let urls = [];
  let topic = "",
    location = "",
    domain = "";
  const sourcePolicy = document.getElementById("inp-source-policy").value || "official_plus_directory";
  const intent = document.getElementById("inp-intent").value.trim();
  const originLocation = document.getElementById("inp-origin-location").value.trim();
  const maxDistanceRaw = parseFloat(document.getElementById("inp-max-distance-km").value);
  const maxDistance = Number.isFinite(maxDistanceRaw) ? maxDistanceRaw : null;
  const minScoreRaw = parseFloat(document.getElementById("inp-min-score").value);
  const minScore = Number.isFinite(minScoreRaw) ? Math.max(0, Math.min(1, minScoreRaw)) : 0.35;
  const perDomainInput = parseInt(document.getElementById("inp-max-per-domain").value, 10);
  const maxPerDomain = Number.isFinite(perDomainInput) ? Math.max(1, Math.min(25, perDomainInput)) : 4;
  document.getElementById("inp-max-per-domain").value = String(maxPerDomain);
  let maxPages = parseInt(document.getElementById("inp-max-pages").value, 10) || 10;

  if (currentMode === "manual") {
    const urlsEl = document.getElementById("inp-urls");
    urls = urlsEl
      ? urlsEl.value
          .split("\n")
          .map((u) => u.trim())
          .filter((u) => u)
      : [];
    if (!urls.length) {
      toast("Enter at least one URL", "error");
      return;
    }
  } else {
    topic = document.getElementById("inp-topic").value.trim();
    location = document.getElementById("inp-location").value.trim();
    domain = document.getElementById("inp-domain").value.trim();
    const discoverInput = parseInt(document.getElementById("inp-discover-pages").value, 10);
    maxPages = Number.isFinite(discoverInput) ? Math.max(1, Math.min(20, discoverInput)) : maxPages;
    document.getElementById("inp-discover-pages").value = String(maxPages);
    if (!topic) {
      toast("Enter a topic", "error");
      return;
    }
  }

  // Build selectors_map
  const { getSelectorsMap } = await import("./analyzer.js");
  const sm = getSelectorsMap();
  let selectorsMap = {};
  if (sm && sm.fields && Object.keys(sm.fields).length > 0) {
    const schemaNames = new Set(schema.map((f) => f.name));
    const filteredFields = {};
    Object.entries(sm.fields).forEach(([name, sel]) => {
      if (schemaNames.has(name)) {
        filteredFields[name] = sel;
      }
    });
    if (Object.keys(filteredFields).length > 0) {
      selectorsMap = { item_container: sm.item_container || "", fields: filteredFields };
    }
  }

  const payload = {
    name,
    mode: currentMode,
    intent,
    urls,
    topic,
    location,
    preferred_domain: domain,
    origin_location: originLocation,
    max_distance_km: maxDistance,
    source_policy: sourcePolicy,
    max_per_domain: maxPerDomain,
    schema_fields: schema,
    filters,
    selectors_map: selectorsMap,
    deduplicate: document.getElementById("chk-dedup")?.checked ?? false,
    deduplicate_field: document.getElementById("inp-dedup-field")?.value?.trim() ?? "",
    pagination: document.getElementById("chk-pagination")?.checked ?? false,
    max_pages: maxPages,
    min_record_score: minScore,
  };

  const btn = document.getElementById("btn-submit");
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Starting...';

  try {
    const res = await apiFetch(`${API}/api/jobs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Failed");
    toast("Job started", "success");
    const { switchView } = await import("./views.js");
    switchView("jobs");
  } catch (err) {
    toast(`Error: ${err.message}`, "error");
  } finally {
    btn.disabled = false;
    btn.innerHTML = "Start Scraping →";
  }
}
