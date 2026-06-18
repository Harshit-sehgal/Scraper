/* ═══════════════════════════════════════════
   DataForge — URL Analyzer
   ═══════════════════════════════════════════ */

import { esc, toast } from "./utils.js";
import { API, apiFetch } from "./api.js";
import { currentMode, setMode } from "./views.js";
import { addField } from "./form.js";

// ─── State ───

let _analyzedFields = [];
let _selectorsMap = null;
let _lastIntelligence = null;
let _lastWorkflowDraft = null;

// ─── Analyze URL ───

export async function analyzeURL() {
  const urlInput = document.getElementById("inp-analyze-url");
  if (!urlInput) return;
  const url = urlInput.value.trim();
  if (!url) {
    toast("Enter a URL to analyze", "error");
    return;
  }

  const btn = document.getElementById("btn-analyze-url");
  const btnText = btn?.querySelector(".analyze-btn-text");
  const spinner = document.getElementById("analyze-spinner");
  const results = document.getElementById("analyze-results");
  const error = document.getElementById("analyze-error");

  results?.classList.add("hidden");
  error?.classList.add("hidden");
  if (btn) btn.disabled = true;
  if (btnText) btnText.textContent = "Analyzing...";
  if (spinner) spinner.classList.remove("hidden");

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 130_000);

  try {
    const res = await apiFetch(`${API}/api/url/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, fetch_preview: false }),
      signal: controller.signal,
    });

    const data = await res.json();

    if (!res.ok || data.error) {
      throw new Error(data.error || data.detail || "Analysis failed");
    }

    const intelligence = data.url_intelligence || data;
    _lastIntelligence = intelligence;

    _analyzedFields = Array.isArray(data.suggested_fields) ? data.suggested_fields : [];

    _selectorsMap = {
      item_container: data.item_container || "",
      fields: {},
    };
    _analyzedFields.forEach((f) => {
      if (f.selector) {
        _selectorsMap.fields[f.name] = {
          selector: f.selector,
          type: f.type || "string",
        };
      }
    });

    renderAnalysisInfo(data);
    renderFieldList();
    renderAcquisitionBanner(data, url);
    renderIntelligencePanel(intelligence);

    results?.classList.remove("hidden");
    toast("URL analysis complete", "success");
  } catch (err) {
    if (error) error.classList.remove("hidden");
    const errorText = document.getElementById("analyze-error-text");
    if (err.name === "AbortError") {
      if (errorText)
        errorText.textContent =
          "Analysis timed out — the page may be too slow or protected by anti-bot measures. Try a different source URL.";
      toast("Analysis timed out", "error");
    } else {
      if (errorText) errorText.textContent = err.message || "Failed to analyze URL";
      toast(`Analysis error: ${err.message}`, "error");
    }
  } finally {
    clearTimeout(timeoutId);
    if (btn) btn.disabled = false;
    if (btnText) btnText.textContent = "Analyze URL";
    if (spinner) spinner.classList.add("hidden");
  }
}

// ─── Render Analysis Info ───

export function renderAnalysisInfo(data) {
  const structureEl = document.getElementById("ai-structure");
  const recordsEl = document.getElementById("ai-records");
  const antibotEl = document.getElementById("ai-antibot");
  const fetchTimeEl = document.getElementById("ai-fetch-time");

  if (structureEl) {
    const structType = data.page_structure || "unknown";
    const structConf = data.structure_confidence ? ` (${(data.structure_confidence * 100).toFixed(0)}%)` : "";
    structureEl.textContent = `${structType}${structConf}`;
  }
  if (recordsEl) {
    recordsEl.textContent = `~${data.estimated_record_count || "?"} records`;
  }
  if (antibotEl) {
    const score = data.anti_bot_score || 0;
    const riskLabel = score < 0.3 ? "Low" : score < 0.6 ? "Medium" : "High";
    const color = score < 0.3 ? "var(--success)" : score < 0.6 ? "var(--warning)" : "var(--danger)";
    antibotEl.textContent = "Anti-bot: ";
    const badge = document.createElement("span");
    badge.style.color = color;
    badge.style.fontWeight = "700";
    badge.textContent = riskLabel;
    const suffix = document.createTextNode(` (${(score * 100).toFixed(0)}%)`);
    antibotEl.appendChild(badge);
    antibotEl.appendChild(suffix);
  }
  if (fetchTimeEl) {
    const ms = data.fetch_time_ms;
    fetchTimeEl.textContent = ms != null ? `\u23F1 ${(ms / 1000).toFixed(1)}s` : "\u23F1 ?s";
  }
}

// ─── Render URL Intelligence Panel ───

export function renderIntelligencePanel(intel) {
  const panel = document.getElementById("url-intelligence-panel");
  if (!panel) return;

  const classificationEl = document.getElementById("intelligence-classification");
  const riskEl = document.getElementById("intelligence-risk");
  const recommendedEl = document.getElementById("intelligence-recommended-mode");
  const reasonEl = document.getElementById("intelligence-reason");
  const confidenceEl = document.getElementById("intelligence-confidence");
  const stepsContainer = document.getElementById("intelligence-steps-container");
  const stepsList = document.getElementById("intelligence-steps");
  const actionsEl = document.getElementById("intelligence-actions");
  const primary = Array.isArray(intel.classifications) ? intel.classifications[0] : null;
  const classification = primary?.type || intel.classification || "unknown";
  const confidence = primary?.confidence ?? intel.confidence;
  const risk = intel.risk_level || intel.risk || "low";
  const recommendedMode = intel.recommended_mode || "unknown";
  const reason = intel.user_message || intel.reason || primary?.evidence || "";

  if (classificationEl) {
    classificationEl.textContent = classification ? classification.replace(/_/g, " ") : "—";
  }
  if (riskEl) {
    riskEl.textContent = risk ? risk.charAt(0).toUpperCase() + risk.slice(1) : "—";
    riskEl.className = `intelligence-value risk-${risk || "low"}`;
  }
  if (recommendedEl) {
    recommendedEl.textContent = recommendedMode ? recommendedMode.replace(/_/g, " ") : "—";
  }
  if (reasonEl) {
    reasonEl.textContent = reason || "—";
  }
  if (confidenceEl) {
    const conf = confidence != null ? `${(confidence * 100).toFixed(0)}% confident` : "";
    confidenceEl.textContent = conf;
  }
  if (stepsContainer && stepsList) {
    if (intel.next_steps && intel.next_steps.length) {
      stepsList.innerHTML = intel.next_steps.map((s) => `<li>${esc(s)}</li>`).join("");
      stepsContainer.classList.remove("hidden");
    } else {
      stepsList.innerHTML = "";
      stepsContainer.classList.add("hidden");
    }
  }

  if (actionsEl) {
    actionsEl.innerHTML = renderIntelligenceActions(recommendedMode);
    actionsEl.classList.toggle("hidden", !actionsEl.innerHTML);
  }

  panel.classList.remove("hidden");
}

function renderIntelligenceActions(recommendedMode) {
  if (recommendedMode === "direct_scrape") {
    return '<button type="button" class="btn primary small" data-action="url-direct-scrape">Continue with Direct Scrape</button>';
  }
  if (recommendedMode === "workflow_replay_recommended") {
    return [
      '<button type="button" class="btn secondary small" data-action="url-direct-scrape">Try Direct Scrape Once</button>',
      '<button type="button" class="btn primary small" data-action="url-create-workflow-draft">Create Reliable Workflow</button>',
    ].join("");
  }
  if (recommendedMode === "auth_profile_recommended") {
    return '<button type="button" class="btn secondary small" data-action="url-auth-profile">Create Auth Profile</button>';
  }
  if (recommendedMode === "blocked_or_unsafe") {
    return '<button type="button" class="btn secondary small" disabled>Blocked by safety policy</button>';
  }
  return '<button type="button" class="btn secondary small" data-action="url-direct-scrape">Review and Continue</button>';
}

export function continueWithDirectScrape() {
  const urlInput = document.getElementById("inp-analyze-url");
  const urlsTextarea = document.getElementById("inp-urls");
  const url = urlInput?.value?.trim() || "";
  if (!url) {
    toast("Enter a URL first", "error");
    return;
  }
  setMode("manual");
  if (urlsTextarea && !urlsTextarea.value.includes(url)) {
    const existing = urlsTextarea.value.trim();
    urlsTextarea.value = existing ? `${existing}\n${url}` : url;
  }
  toast("Direct Scrape URL added", "success");
}

export async function createWorkflowDraftFromAnalysis() {
  const urlInput = document.getElementById("inp-analyze-url");
  const url = urlInput?.value?.trim() || "";
  if (!url) {
    toast("Enter a URL first", "error");
    return;
  }
  const suggested = Array.isArray(_lastIntelligence?.suggested_start_urls)
    ? _lastIntelligence.suggested_start_urls
    : [];
  const selected = suggested[0]?.url || "";
  try {
    const res = await apiFetch(`${API}/api/workflow-drafts/from-url-analysis`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        original_url: url,
        selected_start_url: selected || undefined,
        detected_reason: _lastIntelligence?.user_message || "",
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "Could not create workflow draft");
    if (selected) {
      const urlsTextarea = document.getElementById("inp-urls");
      if (urlsTextarea) urlsTextarea.value = selected;
    }
    _lastWorkflowDraft = data;
    renderWorkflowDraftPanel(data);
    toast("Workflow draft created", "success");
    return data;
  } catch (err) {
    toast(`Workflow draft error: ${err.message}`, "error");
    return null;
  }
}

export function showAuthProfileEntryNotice() {
  toast("Auth Profile setup is recommended for login-required pages", "info");
}

export function renderWorkflowDraftPanel(draft) {
  const panel = document.getElementById("workflow-builder-panel");
  if (!panel || !draft) return;

  const startUrl = draft.selected_start_url || draft.start_url || "";
  const originalUrl = draft.original_url || "";
  const reason = draft.detected_reason || "";
  const fields = Array.isArray(draft.detected_fields) ? draft.detected_fields : [];
  const suggestions = Array.isArray(draft.recommended_start_urls) ? draft.recommended_start_urls : [];

  const statusEl = document.getElementById("workflow-builder-status");
  const startEl = document.getElementById("workflow-builder-start-url");
  const originalEl = document.getElementById("workflow-builder-original-url");
  const reasonEl = document.getElementById("workflow-builder-reason");
  const fieldsEl = document.getElementById("workflow-builder-fields");
  const mappingEl = document.getElementById("workflow-builder-mapping");
  const previewEl = document.getElementById("workflow-builder-preview-table");
  const timelineEl = document.getElementById("workflow-builder-timeline");
  const failureEl = document.getElementById("workflow-builder-failure");

  if (statusEl) statusEl.textContent = draft.status || "draft";
  if (startEl) startEl.value = startUrl;
  if (originalEl) originalEl.textContent = originalUrl || "—";
  if (reasonEl) reasonEl.textContent = reason || "—";
  if (fieldsEl) {
    fieldsEl.innerHTML = fields.length
      ? fields
          .map(
            (field) => `
              <div class="workflow-field-row">
                <span>${esc(field.label || field.selector || "Field")}</span>
                <code>${esc(field.selector || "")}</code>
                <strong>${Math.round((field.confidence || 0) * 100)}%</strong>
              </div>
            `,
          )
          .join("")
      : '<div class="workflow-empty">No fields detected yet</div>';
  }
  if (mappingEl) {
    mappingEl.value = JSON.stringify(
      {
        start_url: startUrl,
        suggested_start_urls: suggestions.map((item) => item.url),
        fields: [],
        submit_action: { action: "click", selector: "" },
      },
      null,
      2,
    );
  }
  if (previewEl) {
    previewEl.innerHTML = '<div class="workflow-empty">No preview run yet</div>';
  }
  if (timelineEl) {
    timelineEl.innerHTML = "<li>Draft created</li>";
  }
  if (failureEl) {
    failureEl.classList.add("hidden");
    failureEl.textContent = "";
  }

  panel.classList.remove("hidden");
}

// ─── Render Field List ───

export function renderFieldList(fields) {
  const fieldList = document.getElementById("analyze-field-list");
  const fieldCount = document.getElementById("analyze-field-count");
  const items = fields ?? _analyzedFields;

  if (fieldCount) fieldCount.textContent = String(items.length);
  if (!fieldList) return;

  if (!items.length) {
    fieldList.innerHTML = '<div class="empty"><p>No data fields detected on this page</p></div>';
  } else {
    fieldList.innerHTML = items
      .map((f, i) => {
        const conf = Math.min(f.confidence || 0.5, 1.0);
        const confPct = Math.round(conf * 100);
        const example = f.example_value ? String(f.example_value).slice(0, 60) : "";
        const typeLabel = f.type || "string";
        return `
                <div class="analyze-field-item selected" data-index="${i}" data-action="toggle-field-item">
                    <input type="checkbox" class="analyze-field-checkbox" checked data-index="${i}">
                    <span class="analyze-field-name">${esc(f.name)}</span>
                    <span class="analyze-field-type">${esc(typeLabel)}</span>
                    ${example ? `<span class="analyze-field-example">${esc(example)}</span>` : ""}
                    <span class="analyze-field-confidence">
                        ${confPct}%
                        <span class="conf-bar"><span class="conf-bar-fill" style="width:${confPct}%"></span></span>
                    </span>
                </div>
            `;
      })
      .join("");
  }
}

// ─── Render Acquisition Banner ───

export function renderAcquisitionBanner(data, url) {
  const acqBanner = document.getElementById("acquisition-banner");
  if (!acqBanner) return;

  const lineage = data.acquisition_lineage || {};
  const state = lineage.state || "direct";
  const userMsg = data.user_message || lineage.user_message || "";
  const sessionBound = data.session_detection?.is_session_bound || lineage.session_bound || false;
  const emptyCheck = data.empty_check || {};
  const canonicalUrl = data.canonical_url || "";

  let bannerClass = "direct";
  let bannerText = userMsg || "Page loaded successfully.";

  if (state === "recovered") {
    bannerClass = "recovered";
  } else if (state === "session_expired" || state === "recovery_failed" || state === "no_search_form") {
    bannerClass = "expired";
  } else if (state === "empty_response" || emptyCheck.is_empty) {
    bannerClass = "empty";
  } else if (sessionBound && state !== "recovered") {
    bannerClass = "session";
  }

  const isSessionBound =
    state !== "recovered" && (sessionBound || (data.session_detection?.ephemeral_params || []).length > 0);

  const frag = document.createDocumentFragment();

  const b = document.createElement("strong");
  b.textContent = bannerText;
  frag.appendChild(b);

  if (canonicalUrl && canonicalUrl !== url) {
    const line = document.createElement("br");
    const small = document.createElement("small");
    small.style.opacity = "0.7";
    small.textContent = `Canonical: ${canonicalUrl}`;
    frag.appendChild(line);
    frag.appendChild(small);
  }
  if (state === "recovered") {
    const line = document.createElement("br");
    const small = document.createElement("small");
    small.style.opacity = "0.7";
    small.textContent = "Recovered fresh results via search form submission";
    frag.appendChild(line);
    frag.appendChild(small);
  }
  if (isSessionBound) {
    const line = document.createElement("br");
    const small = document.createElement("small");
    small.style.opacity = "0.7";
    small.textContent = "Original URL contained ephemeral session parameters";
    frag.appendChild(line);
    frag.appendChild(small);
  }
  if (emptyCheck.is_empty) {
    const line = document.createElement("br");
    const small = document.createElement("small");
    small.style.opacity = "0.7";
    small.textContent = emptyCheck.message || "Page returned 200 but contained no useful data";
    frag.appendChild(line);
    frag.appendChild(small);
    if (emptyCheck.suggestions && emptyCheck.suggestions.length) {
      const line2 = document.createElement("br");
      const small2 = document.createElement("small");
      small2.style.opacity = "0.7";
      small2.textContent = `Suggestion: ${emptyCheck.suggestions[0]}`;
      frag.appendChild(line2);
      frag.appendChild(small2);
    }
  }

  acqBanner.className = `acquisition-banner ${bannerClass}`;
  acqBanner.innerHTML = "";
  acqBanner.appendChild(frag);
  acqBanner.classList.remove("hidden");
}

// ─── Toggle Fields ───

export function toggleAllFields(select) {
  const checkboxes = document.querySelectorAll(".analyze-field-checkbox");
  const items = document.querySelectorAll(".analyze-field-item");
  checkboxes.forEach((cb, i) => {
    cb.checked = select;
    if (items[i]) items[i].classList.toggle("selected", select);
  });
}

// ─── Apply Fields ───

export async function applyAnalyzedFields() {
  const checkboxes = document.querySelectorAll(".analyze-field-checkbox:checked");
  if (!checkboxes.length) {
    toast("Select at least one field to apply", "error");
    return;
  }

  const selected = [];
  checkboxes.forEach((cb) => {
    const idx = parseInt(cb.dataset.index, 10);
    if (!isNaN(idx) && _analyzedFields[idx]) {
      selected.push(_analyzedFields[idx]);
    }
  });

  if (!selected.length) {
    toast("No valid fields selected", "error");
    return;
  }

  const schemaContainer = document.getElementById("schema-container");
  if (schemaContainer) schemaContainer.innerHTML = "";

  selected.forEach((f) => {
    addField({
      name: f.name,
      field_type: f.type || "string",
      description: f.description || f.example_value || "",
    });
  });

  // Pre-populate URLs textarea
  const urlInput = document.getElementById("inp-analyze-url");
  const urlsTextarea = document.getElementById("inp-urls");
  if (urlInput && urlsTextarea && currentMode === "manual") {
    const url = urlInput.value.trim();
    if (url && !urlsTextarea.value.includes(url)) {
      const existing = urlsTextarea.value.trim();
      urlsTextarea.value = existing ? existing + "\n" + url : url;
    }
  }

  toast(`Applied ${selected.length} fields to schema`, "success");
  document.getElementById("schema-container").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

// ─── Clear Analysis ───

export function clearAnalysis() {
  _analyzedFields = [];
  _selectorsMap = null;
  _lastIntelligence = null;
  _lastWorkflowDraft = null;
  const results = document.getElementById("analyze-results");
  if (results) results.classList.add("hidden");
  const error = document.getElementById("analyze-error");
  if (error) error.classList.add("hidden");
  const urlInput = document.getElementById("inp-analyze-url");
  if (urlInput) urlInput.value = "";
  const intelPanel = document.getElementById("url-intelligence-panel");
  if (intelPanel) intelPanel.classList.add("hidden");
  const workflowPanel = document.getElementById("workflow-builder-panel");
  if (workflowPanel) workflowPanel.classList.add("hidden");
}

// ─── Expose selectors map for form submission ───

export function getSelectorsMap() {
  return _selectorsMap;
}
export function getAnalyzedFields() {
  return _analyzedFields;
}
export function getWorkflowDraft() {
  return _lastWorkflowDraft;
}
