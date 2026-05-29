/* ═══════════════════════════════════════════
   DataForge — URL Analyzer
   ═══════════════════════════════════════════ */

import { esc, toast } from './utils.js';
import { API, apiFetch } from './api.js';

// ─── State ───

let _analyzedFields = [];
let _selectorsMap = null;

// ─── Analyze URL ───

export async function analyzeURL() {
    const urlInput = document.getElementById('inp-analyze-url');
    const url = urlInput.value.trim();
    if (!url) {
        toast('Enter a URL to analyze', 'error');
        return;
    }

    const btn = document.getElementById('btn-analyze-url');
    const btnText = btn.querySelector('.analyze-btn-text');
    const spinner = document.getElementById('analyze-spinner');
    const results = document.getElementById('analyze-results');
    const error = document.getElementById('analyze-error');

    results.classList.add('hidden');
    error.classList.add('hidden');
    btn.disabled = true;
    if (btnText) btnText.textContent = 'Analyzing...';
    if (spinner) spinner.classList.remove('hidden');

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 130_000);

    try {
        const res = await apiFetch(`${API}/api/url/analyze`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url }),
            signal: controller.signal
        });

        const data = await res.json();

        if (!res.ok || data.error) {
            throw new Error(data.error || (data.detail || 'Analysis failed'));
        }

        _analyzedFields = Array.isArray(data.suggested_fields) ? data.suggested_fields : [];

        _selectorsMap = {
            item_container: data.item_container || '',
            fields: {}
        };
        _analyzedFields.forEach(f => {
            if (f.selector) {
                _selectorsMap.fields[f.name] = {
                    selector: f.selector,
                    type: f.type || 'string'
                };
            }
        });

        renderAnalysisInfo(data);
        renderFieldList();
        renderAcquisitionBanner(data, url);

        results.classList.remove('hidden');
        toast(`Found ${_analyzedFields.length} fields on ${url}`, 'success');
    } catch (err) {
        error.classList.remove('hidden');
        if (err.name === 'AbortError') {
            document.getElementById('analyze-error-text').textContent =
                'Analysis timed out — the page may be too slow or protected by anti-bot measures. Try a different source URL.';
            toast('Analysis timed out', 'error');
        } else {
            document.getElementById('analyze-error-text').textContent = err.message || 'Failed to analyze URL';
            toast(`Analysis error: ${err.message}`, 'error');
        }
    } finally {
        clearTimeout(timeoutId);
        btn.disabled = false;
        if (btnText) btnText.textContent = 'Analyze URL';
        if (spinner) spinner.classList.add('hidden');
    }
}

// ─── Render Analysis Info ───

function renderAnalysisInfo(data) {
    const structureEl = document.getElementById('ai-structure');
    const recordsEl = document.getElementById('ai-records');
    const antibotEl = document.getElementById('ai-antibot');
    const fetchTimeEl = document.getElementById('ai-fetch-time');

    if (structureEl) {
        const structType = data.page_structure || 'unknown';
        const structConf = data.structure_confidence ? ` (${(data.structure_confidence * 100).toFixed(0)}%)` : '';
        structureEl.textContent = `📐 ${structType}${structConf}`;
    }
    if (recordsEl) {
        recordsEl.textContent = `📊 ~${data.estimated_record_count || '?'} records`;
    }
    if (antibotEl) {
        const score = data.anti_bot_score || 0;
        const riskLabel = score < 0.3 ? 'Low' : score < 0.6 ? 'Medium' : 'High';
        const color = score < 0.3 ? '#1f9a5f' : score < 0.6 ? '#c7851b' : '#d24646';
        antibotEl.innerHTML = `🛡️ Anti-bot: <span style="color:${color};font-weight:700;">${riskLabel}</span> (${(score * 100).toFixed(0)}%)`;
    }
    if (fetchTimeEl) {
        fetchTimeEl.textContent = `⏱️ ${(data.fetch_time_ms / 1000).toFixed(1)}s`;
    }
}

// ─── Render Field List ───

function renderFieldList() {
    const fieldList = document.getElementById('analyze-field-list');
    const fieldCount = document.getElementById('analyze-field-count');

    if (fieldCount) fieldCount.textContent = String(_analyzedFields.length);

    if (!_analyzedFields.length) {
        fieldList.innerHTML = '<div class="empty"><p>No data fields detected on this page</p></div>';
    } else {
        fieldList.innerHTML = _analyzedFields.map((f, i) => {
            const conf = Math.min(f.confidence || 0.5, 1.0);
            const confPct = Math.round(conf * 100);
            const example = f.example_value ? String(f.example_value).slice(0, 60) : '';
            const typeLabel = f.type || 'string';
            return `
                <div class="analyze-field-item selected" data-index="${i}" data-action="toggle-field-item">
                    <input type="checkbox" class="analyze-field-checkbox" checked data-index="${i}">
                    <span class="analyze-field-name">${esc(f.name)}</span>
                    <span class="analyze-field-type">${esc(typeLabel)}</span>
                    ${example ? `<span class="analyze-field-example">${esc(example)}</span>` : ''}
                    <span class="analyze-field-confidence">
                        ${confPct}%
                        <span class="conf-bar"><span class="conf-bar-fill" style="width:${confPct}%"></span></span>
                    </span>
                </div>
            `;
        }).join('');
    }
}

// ─── Render Acquisition Banner ───

function renderAcquisitionBanner(data, url) {
    const acqBanner = document.getElementById('acquisition-banner');
    if (!acqBanner) return;

    const lineage = data.acquisition_lineage || {};
    const state = lineage.state || 'direct';
    const userMsg = data.user_message || lineage.user_message || '';
    const sessionBound = data.session_detection?.is_session_bound || lineage.session_bound || false;
    const emptyCheck = data.empty_check || {};
    const canonicalUrl = data.canonical_url || '';

    let bannerClass = 'direct';
    let bannerText = userMsg || 'Page loaded successfully.';

    if (state === 'recovered') {
        bannerClass = 'recovered';
    } else if (state === 'session_expired' || state === 'recovery_failed' || state === 'no_search_form') {
        bannerClass = 'expired';
    } else if (state === 'empty_response' || emptyCheck.is_empty) {
        bannerClass = 'empty';
    } else if (sessionBound && state !== 'recovered') {
        bannerClass = 'session';
    }

    const isSessionBound = state !== 'recovered' && (sessionBound || (data.session_detection?.ephemeral_params || []).length > 0);

    let bannerHTML = `<strong>${esc(bannerText)}</strong>`;
    if (canonicalUrl && canonicalUrl !== url) {
        bannerHTML += `<br><small style="opacity:0.7">Canonical: ${esc(canonicalUrl)}</small>`;
    }
    if (state === 'recovered') {
        bannerHTML += `<br><small style="opacity:0.7">Recovered fresh results via search form submission</small>`;
    }
    if (isSessionBound) {
        bannerHTML += `<br><small style="opacity:0.7">Original URL contained ephemeral session parameters</small>`;
    }
    if (emptyCheck.is_empty) {
        bannerHTML += `<br><small style="opacity:0.7">${esc(emptyCheck.message || 'Page returned 200 but contained no useful data')}</small>`;
        if (emptyCheck.suggestions && emptyCheck.suggestions.length) {
            bannerHTML += `<br><small style="opacity:0.7">Suggestion: ${esc(emptyCheck.suggestions[0])}</small>`;
        }
    }

    acqBanner.className = `acquisition-banner ${bannerClass}`;
    acqBanner.innerHTML = bannerHTML;
    acqBanner.classList.remove('hidden');
}

// ─── Toggle Fields ───

export function toggleAllFields(select) {
    const checkboxes = document.querySelectorAll('.analyze-field-checkbox');
    const items = document.querySelectorAll('.analyze-field-item');
    checkboxes.forEach((cb, i) => {
        cb.checked = select;
        if (items[i]) items[i].classList.toggle('selected', select);
    });
}

// ─── Apply Fields ───

export async function applyAnalyzedFields() {
    const checkboxes = document.querySelectorAll('.analyze-field-checkbox:checked');
    if (!checkboxes.length) {
        toast('Select at least one field to apply', 'error');
        return;
    }

    const selected = [];
    checkboxes.forEach(cb => {
        const idx = parseInt(cb.dataset.index, 10);
        if (!isNaN(idx) && _analyzedFields[idx]) {
            selected.push(_analyzedFields[idx]);
        }
    });

    if (!selected.length) {
        toast('No valid fields selected', 'error');
        return;
    }

    const schemaContainer = document.getElementById('schema-container');
    schemaContainer.innerHTML = '';

    const { addField } = await import('./form.js');
    selected.forEach(f => {
        addField({
            name: f.name,
            field_type: f.type || 'string',
            description: f.description || f.example_value || ''
        });
    });

    // Pre-populate URLs textarea
    const urlInput = document.getElementById('inp-analyze-url');
    const urlsTextarea = document.getElementById('inp-urls');
    const { currentMode } = await import('./views.js');
    if (urlInput && urlsTextarea && currentMode === 'manual') {
        const url = urlInput.value.trim();
        if (url && !urlsTextarea.value.includes(url)) {
            const existing = urlsTextarea.value.trim();
            urlsTextarea.value = existing ? existing + '\n' + url : url;
        }
    }

    toast(`Applied ${selected.length} fields to schema`, 'success');
    document.getElementById('schema-container').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// ─── Clear Analysis ───

export function clearAnalysis() {
    _analyzedFields = [];
    _selectorsMap = null;
    document.getElementById('analyze-results').classList.add('hidden');
    document.getElementById('analyze-error').classList.add('hidden');
    document.getElementById('inp-analyze-url').value = '';
}

// ─── Expose selectors map for form submission ───

export function getSelectorsMap() { return _selectorsMap; }
export function getAnalyzedFields() { return _analyzedFields; }
