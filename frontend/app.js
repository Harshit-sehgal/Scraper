/* ═══════════════════════════════════════════
   DataForge — Frontend App Logic v2
   ═══════════════════════════════════════════ */

const API = (() => {
    // Allow explicit override, then prefer same-origin when backend is served on :8000.
    const explicit = typeof window.DATAFORGE_API_BASE === 'string' ? window.DATAFORGE_API_BASE.trim() : '';
    if (explicit) return explicit.replace(/\/$/, '');

    const { protocol, hostname, port, origin } = window.location;
    if (protocol === 'http:' || protocol === 'https:') {
        // In local multi-port dev, frontend often runs on 3000/5173 while API is on 8000.
        if ((hostname === 'localhost' || hostname === '127.0.0.1') && port !== '8000') {
            return 'http://127.0.0.1:8000';
        }
        return origin;
    }
    // file:// or unknown protocol fallback for local static preview.
    return 'http://127.0.0.1:8000';
})();
const UI_STATE_KEY = 'dataforge_ui_state_v1';
let currentJobId = null;
let currentMode = "manual";
let currentView = 'jobs';
let pollers = {};
let jobsCache = [];
let currentResultsCache = [];
let statusTimer = null;
let jobsUpdatedAt = 0;

function readUIState() {
    try {
        const raw = localStorage.getItem(UI_STATE_KEY);
        return raw ? JSON.parse(raw) : {};
    } catch {
        return {};
    }
}

function writeUIState(patch) {
    try {
        const next = { ...readUIState(), ...(patch || {}) };
        localStorage.setItem(UI_STATE_KEY, JSON.stringify(next));
    } catch {
        // Ignore storage errors (private mode, quota, etc.)
    }
}

// ─── View / Tab Switching ───

function switchView(name) {
    currentView = name;
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.getElementById(`view-${name}`).classList.add('active');

    const tabMap = { jobs: 'tab-jobs', new: 'tab-new', results: 'tab-jobs', recycle: 'tab-recycle', cognition: 'tab-cognition' };
    const tabEl = document.getElementById(tabMap[name]);
    if (tabEl) tabEl.classList.add('active');

    if (name === 'jobs') refreshJobs();
    if (name === 'new') initForm();
    if (name === 'recycle') refreshRecycleBin();
    if (name === 'cognition') refreshCognition();

    writeUIState({ view: name });
}

document.querySelectorAll('.tab').forEach(t => {
    t.addEventListener('click', () => switchView(t.dataset.view));
});

// ─── Mode Toggle ───

function setMode(mode) {
    currentMode = mode;
    document.querySelectorAll('#mode-toggle .toggle').forEach(t => {
        t.classList.toggle('active', t.dataset.mode === mode);
    });
    document.getElementById('section-manual').classList.toggle('hidden', mode !== 'manual');
    document.getElementById('section-auto').classList.toggle('hidden', mode !== 'auto');
}

// ─── Toast ───

function toast(msg, type = 'info') {
    const c = document.getElementById('toasts');
    const t = document.createElement('div');
    t.className = `toast ${type}`;
    t.textContent = msg;
    c.appendChild(t);
    setTimeout(() => t.remove(), 4000);
}

function setEngineStatus(text, offline = false) {
    const el = document.getElementById('engine-status');
    const textEl = document.getElementById('engine-status-text');
    if (!el || !textEl) return;
    textEl.textContent = text;
    el.classList.toggle('offline', offline);
}

async function refreshSystemStatus() {
    try {
        const r = await fetch(`${API}/api/system/status`);
        if (!r.ok) throw new Error('status unavailable');
        const data = await r.json();
        const active = Number((data.jobs || {}).active || 0);
        setEngineStatus(active > 0 ? `Online • ${active} active` : 'Online • Idle');
    } catch (e) {
        setEngineStatus('Offline', true);
    }
}

function updateJobsLastUpdatedLabel(forceText = '') {
    const el = document.getElementById('jobs-last-updated');
    if (!el) return;

    if (forceText) {
        el.textContent = forceText;
        return;
    }

    if (!jobsUpdatedAt) {
        el.textContent = 'Never updated';
        return;
    }

    const diffSec = Math.max(0, Math.floor((Date.now() - jobsUpdatedAt) / 1000));
    if (diffSec < 5) {
        el.textContent = 'Updated just now';
        return;
    }
    if (diffSec < 60) {
        el.textContent = `Updated ${diffSec}s ago`;
        return;
    }
    const mins = Math.floor(diffSec / 60);
    el.textContent = `Updated ${mins}m ago`;
}

function isTypingTarget(target) {
    if (!target) return false;
    const tag = String(target.tagName || '').toLowerCase();
    return tag === 'input' || tag === 'textarea' || tag === 'select' || target.isContentEditable;
}

function onGlobalKeydown(e) {
    const typing = isTypingTarget(e.target);
    const jobsSearch = document.getElementById('jobs-search');
    const resultSearch = document.getElementById('inp-result-search');

    if (!typing && e.key === 'n') {
        e.preventDefault();
        switchView('new');
        const nameInput = document.getElementById('inp-name');
        if (nameInput) nameInput.focus();
        return;
    }

    if (!typing && e.key === '/') {
        e.preventDefault();
        const inResults = document.getElementById('view-results')?.classList.contains('active');
        const inNew = document.getElementById('view-new')?.classList.contains('active');
        const target = inResults
            ? resultSearch
            : (inNew ? document.getElementById('inp-intent') : jobsSearch);
        if (target) {
            target.focus();
            target.select();
        }
        return;
    }

    if (e.key === 'Escape') {
        if (document.activeElement === jobsSearch && jobsSearch?.value) {
            jobsSearch.value = '';
            onJobsFilterChanged();
            e.preventDefault();
            return;
        }

        if (document.activeElement === resultSearch && resultSearch?.value) {
            resultSearch.value = '';
            renderFilteredResults();
            e.preventDefault();
        }
    }
}

// ─── Jobs: Refresh ───

async function refreshJobs() {
    try {
        const res = await fetch(`${API}/api/jobs`);
        const data = await res.json();
        jobsCache = Array.isArray(data.jobs) ? data.jobs : [];
        renderJobs(applyJobFilters(jobsCache));
        updateKPIs(jobsCache);
        syncPollers(jobsCache);
        jobsUpdatedAt = Date.now();
        updateJobsLastUpdatedLabel();
    } catch (e) {
        setEngineStatus('Offline', true);
        updateJobsLastUpdatedLabel('Unable to refresh');
        /* server might not be ready */
    }
}

async function refreshJobsManual() {
    const btn = document.getElementById('btn-refresh-jobs');
    const prevText = btn ? btn.textContent : '';
    if (btn) {
        btn.disabled = true;
        btn.textContent = 'Refreshing...';
    }

    try {
        await refreshJobs();
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = prevText || 'Refresh';
        }
    }
}

function syncPollers(jobs) {
    const activeIds = new Set(
        jobs
            .filter(j => ['running', 'pending', 'discovering'].includes(j.status))
            .map(j => j.id)
    );

    Object.keys(pollers).forEach(id => {
        if (!activeIds.has(id)) {
            clearInterval(pollers[id]);
            delete pollers[id];
        }
    });

    activeIds.forEach(id => {
        if (!pollers[id]) {
            const pollInterval = (typeof window.DATAFORGE_POLL_JOB_INTERVAL === 'number') ? window.DATAFORGE_POLL_JOB_INTERVAL : 3000;
            pollers[id] = setInterval(() => pollJob(id), pollInterval);
        }
    });
}

function applyJobFilters(jobs) {
    const q = (document.getElementById('jobs-search')?.value || '').trim().toLowerCase();
    const status = (document.getElementById('jobs-status-filter')?.value || 'all').toLowerCase();

    return jobs.filter(j => {
        const name = String(j.name || '').toLowerCase();
        const topic = String(j.topic || '').toLowerCase();
        const statusMatch = status === 'all' || String(j.status || '').toLowerCase() === status;
        const queryMatch = !q || name.includes(q) || topic.includes(q);
        return statusMatch && queryMatch;
    });
}

function onJobsFilterChanged() {
    const jobsSearch = document.getElementById('jobs-search');
    const jobsStatus = document.getElementById('jobs-status-filter');
    writeUIState({
        jobsSearch: jobsSearch ? jobsSearch.value : '',
        jobsStatus: jobsStatus ? jobsStatus.value : 'all',
    });
    renderJobs(applyJobFilters(jobsCache));
}

function updateKPIs(jobs) {
    document.getElementById('kpi-total').textContent = jobs.length;
    document.getElementById('kpi-running').textContent = jobs.filter(j => j.status === 'running' || j.status === 'discovering' || j.status === 'pending').length;
    document.getElementById('kpi-done').textContent = jobs.filter(j => j.status === 'completed' || j.status === 'canceled').length;
    document.getElementById('kpi-records').textContent = jobs.reduce((s, j) => s + (j.filtered_records || 0), 0);
}

function renderJobs(jobs) {
    const list = document.getElementById('jobs-list');
    const empty = document.getElementById('empty-state');

    if (!jobs.length) {
        list.innerHTML = '';
        list.appendChild(empty);
        empty.classList.remove('hidden');
        return;
    }

    list.innerHTML = jobs.map(j => {
        const isActive = ['pending', 'discovering', 'running'].includes(j.status);
        const hasProgress = j.progress_total > 0;
        const pct = hasProgress ? Math.round((j.progress_current / j.progress_total) * 100) : 0;
        
        return `
            <div class="job-row">
                <div class="job-name-col">
                    <div class="job-name">
                        ${esc(j.name)}
                        <span class="mode-tag">${j.mode === 'auto' ? 'auto' : 'manual'}</span>
                    </div>
                    ${isActive && hasProgress ? `
                        <div class="job-progress-wrap">
                            <div class="job-progress-bar" style="width: ${pct}%"></div>
                            <span class="job-progress-text">${pct}%</span>
                        </div>
                    ` : ''}
                </div>
                <div class="job-urls">${j.urls.length} URL${j.urls.length !== 1 ? 's' : ''}</div>
                <div><span class="badge ${j.status}">${j.status}</span></div>
                <div class="job-records">${j.total_records > 0 ? `${j.filtered_records}` : '—'}</div>
                <div class="job-actions">
                    ${j.status === 'completed' ? `<button class="btn ghost small" onclick="viewResults('${j.id}')">View</button>` : ''}
                    ${isActive ? `<button class="btn warn-ghost small" onclick="cancelJob('${j.id}')">Cancel</button>` : ''}
                    <button class="btn danger-ghost small" onclick="deleteJob('${j.id}')">✕</button>
                </div>
            </div>
        `;
    }).join('');
}

async function pollJob(id) {
    try {
        const r = await fetch(`${API}/api/jobs/${id}`);
        if (!r.ok) return;
        const j = await r.json();

        // If we are looking at this job's results, refresh the logs/results
        if (currentView === 'results' && currentJobId === id) {
            // Update logs even while running
            const logsPanel = document.getElementById('logs-panel');
            if (Array.isArray(j.logs) && j.logs.length) {
                logsPanel.classList.remove('hidden');
                renderLogs(j.logs);
            }

            // Update progress bar
            const resProgWrap = document.getElementById('res-progress-wrap');
            if (j.progress_total > 0) {
                resProgWrap.classList.remove('hidden');
                const pct = Math.round((j.progress_current / j.progress_total) * 100);
                document.getElementById('res-progress-bar').style.width = `${pct}%`;
                document.getElementById('res-progress-text').textContent = `${pct}%`;
            } else {
                resProgWrap.classList.add('hidden');
            }
            
            // If it's done, fully refresh to get results
            if (j.status === 'completed' || j.status === 'failed' || j.status === 'canceled') {
                viewResults(id);
            }
        }

        if (j.status === 'completed' || j.status === 'failed' || j.status === 'canceled') {
            clearInterval(pollers[id]);
            delete pollers[id];
            refreshJobs();
            if (j.status === 'completed') toast(`"${j.name}" done — ${j.filtered_records} records`, 'success');
            else if (j.status === 'canceled') toast(`"${j.name}" canceled`, 'info');
            else toast(`"${j.name}" failed: ${j.error}`, 'error');
        }
    } catch (e) { /* ignore */ }
}

async function cancelJob(id) {
    if (!confirm('Cancel this running job?')) return;
    try {
        const r = await fetch(`${API}/api/jobs/${id}/cancel`, { method: 'POST' });
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(data.detail || 'Cancel failed');
        toast(data.message || 'Cancellation requested', 'info');
        refreshJobs();
    } catch (e) {
        toast(`Cancel failed: ${e.message}`, 'error');
    }
}

async function deleteJob(id) {
    if (!confirm('Delete this job?')) return;
    try {
        const r = await fetch(`${API}/api/jobs/${id}`, { method: 'DELETE' });
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(data.detail || 'Delete failed');
        toast('Job deleted');
        refreshJobs();
    } catch (e) {
        toast(`Delete failed: ${e.message}`, 'error');
    }
}

async function clearTerminalJobs() {
    const keepRecent = 5;
    if (!confirm(`Clear completed/failed/canceled jobs and keep the latest ${keepRecent}?`)) return;

    try {
        const r = await fetch(`${API}/api/jobs/cleanup/terminal?keep_recent=${keepRecent}`, { method: 'DELETE' });
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(data.detail || 'Terminal cleanup failed');
        toast(data.message || 'Terminal jobs cleared', 'info');
        refreshJobs();
    } catch (e) {
        toast(`Cleanup failed: ${e.message}`, 'error');
    }
}

async function refreshRecycleBin() {
    try {
        const r = await fetch(`${API}/api/recycle_bin`);
        if (!r.ok) throw new Error('Failed to load recycle bin');
        const data = await r.json();
        const jobs = Array.isArray(data.jobs) ? data.jobs : [];
        
        const list = document.getElementById('recycle-list');
        const empty = document.getElementById('empty-recycle-state');

        if (!jobs.length) {
            list.innerHTML = '';
            list.appendChild(empty);
            empty.classList.remove('hidden');
            return;
        }

        list.innerHTML = jobs.map(j => `
            <div class="job-row recycle-row">
                <div class="job-name recycle-name">
                    ${esc(j.name)}
                </div>
                <div><span class="badge ${j.status}">${j.status}</span></div>
                <div class="job-records">${j.total_records > 0 ? `${j.filtered_records}` : '—'}</div>
                <div class="job-actions">
                    <button class="btn ghost small" onclick="restoreJob('${j.id}')">Restore</button>
                    <button class="btn danger-ghost small" onclick="hardDeleteJob('${j.id}')">Delete Forever</button>
                </div>
            </div>
        `).join('');
    } catch (e) {
        toast(`Failed to load recycle bin: ${e.message}`, 'error');
    }
}

async function restoreJob(id) {
    try {
        const r = await fetch(`${API}/api/recycle_bin/${id}/restore`, { method: 'POST' });
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(data.detail || 'Restore failed');
        toast('Job restored');
        refreshRecycleBin();
    } catch (e) {
        toast(`Restore failed: ${e.message}`, 'error');
    }
}

async function hardDeleteJob(id) {
    if (!confirm('Permanently delete this job? This cannot be undone.')) return;
    try {
        const r = await fetch(`${API}/api/recycle_bin/${id}`, { method: 'DELETE' });
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(data.detail || 'Permanent delete failed');
        toast('Job permanently deleted', 'error');
        refreshRecycleBin();
    } catch (e) {
        toast(`Permanent delete failed: ${e.message}`, 'error');
    }
}

async function clearRecycleBin() {
    if (!confirm('Empty entire recycle bin? This cannot be undone.')) return;

    try {
        const r = await fetch(`${API}/api/recycle_bin`, { method: 'DELETE' });
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(data.detail || 'Failed to clear recycle bin');
        toast(data.message || 'Recycle bin cleared', 'info');
        refreshRecycleBin();
    } catch (e) {
        toast(`Recycle clear failed: ${e.message}`, 'error');
    }
}

// ─── Results ───

async function viewResults(id) {
    currentJobId = id;
    switchView('results');
    try {
        const r = await fetch(`${API}/api/jobs/${id}`);
        const j = await r.json();
        document.getElementById('res-title').textContent = j.name;
        document.getElementById('res-meta').textContent = `${j.filtered_records} records extracted (${j.total_records} total)`;
        document.getElementById('export-group').style.display = j.results.length ? 'flex' : 'none';
        const tableWrap = document.querySelector('#view-results .table-wrap');
        if (tableWrap) tableWrap.scrollLeft = 0;
        
        const aiPanel = document.getElementById('ai-insight-panel');
        if (j.analysis) {
            aiPanel.classList.remove('hidden');
            document.getElementById('ai-insight-text').textContent = j.analysis;
        } else {
            aiPanel.classList.add('hidden');
        }

        const logsPanel = document.getElementById('logs-panel');
        if (Array.isArray(j.logs) && j.logs.length) {
            logsPanel.classList.remove('hidden');
            renderLogs(j.logs);
        } else {
            logsPanel.classList.add('hidden');
        }

        const qualityPanel = document.getElementById('quality-panel');
        const qualityText = document.getElementById('quality-text');
        if (j.quality_report && typeof j.quality_report === 'object') {
            qualityPanel.classList.remove('hidden');
            const qr = j.quality_report;
            const radius = qr.radius || {};
            const integrity = qr.type_integrity || {};
            const sourceBreakdown = qr.source_breakdown || {};
            const sourceAI = qr.ai_source_prediction || {};
            const aiStruct = qr.ai_structuring || {};
            const reclean = qr.reclean || {};
            const overall = Number.isFinite(Number(qr.overall_score)) ? Number(qr.overall_score).toFixed(3) : 'n/a';
            const radiusPart = radius.applied
                ? `Radius kept ${radius.kept}/${(radius.kept || 0) + (radius.dropped || 0)} records`
                : `Radius not applied (${radius.reason || 'not configured'})`;
            const integrityPart = `Type mismatches: ${integrity.total_type_mismatches || 0} across ${integrity.records_with_type_mismatch || 0} records`;
            const sourcePart = `Sources: official ${sourceBreakdown.official || 0}, directory ${sourceBreakdown.directory || 0}, social ${sourceBreakdown.social || 0}`;
            const sourceAIPart = `Source-level AI mapping: ${sourceAI.records_ai_structured || 0}/${sourceAI.records_processed || 0} rows across ${sourceAI.sources_with_ai_structuring || 0}/${sourceAI.sources_attempted || 0} sources`;
            const aiStructPart = aiStruct.applied
                ? `AI structuring: ${aiStruct.ai_chunks || 0}/${aiStruct.total_chunks || 0} chunks with model output`
                : 'AI structuring not applied';
            const noiseRemoved = (aiStruct.noise_rows_removed || 0) + ((reclean.ai_structuring || {}).noise_rows_removed || 0);
            const noisePart = `Noise rows removed: ${noiseRemoved}`;
            const recleanPart = reclean.applied
                ? `Re-cleaned: ${reclean.before_records || 0} -> ${reclean.after_records || 0}`
                : 'Re-clean not run';
            qualityText.textContent = `Overall: ${overall} | Average score: ${qr.avg_record_score || 0} | Final avg: ${qr.avg_final_record_score || 0} | Below threshold: ${qr.records_below_threshold || 0}. ${integrityPart}. ${sourcePart}. ${sourceAIPart}. ${aiStructPart}. ${noisePart}. ${recleanPart}. ${radiusPart}.`;
        } else {
            qualityPanel.classList.add('hidden');
            qualityText.textContent = '';
        }

        const isActive = ['pending', 'discovering', 'running'].includes(j.status);
        const resProgWrap = document.getElementById('res-progress-wrap');
        if (isActive && j.progress_total > 0) {
            resProgWrap.classList.remove('hidden');
            const pct = Math.round((j.progress_current / j.progress_total) * 100);
            document.getElementById('res-progress-bar').style.width = `${pct}%`;
            document.getElementById('res-progress-text').textContent = `${pct}%`;
        } else {
            resProgWrap.classList.add('hidden');
        }

        currentResultsCache = Array.isArray(j.results) ? j.results : [];
        const resultSearch = document.getElementById('inp-result-search');
        if (resultSearch) resultSearch.value = '';
        renderFilteredResults();
        syncResultsScrollSlider();
    } catch (e) {
        toast('Failed to load results', 'error');
    }
}

function applyResultSearch(rows) {
    const q = (document.getElementById('inp-result-search')?.value || '').trim().toLowerCase();
    if (!q) return rows;

    return rows.filter(row => Object.values(row || {}).some(value => {
        const normalized = Array.isArray(value) ? value.join(' ') : value;
        return String(normalized ?? '').toLowerCase().includes(q);
    }));
}

function renderFilteredResults() {
    const filtered = applyResultSearch(currentResultsCache);
    const emptyMessage = currentResultsCache.length && !filtered.length
        ? 'No matching rows for this filter'
        : 'No results';

    renderTable(filtered, emptyMessage);

    const label = document.getElementById('result-count-label');
    if (label) {
        label.textContent = `${filtered.length} of ${currentResultsCache.length} rows`;
    }

    syncResultsScrollSlider();
}

function syncResultsScrollSlider() {
    const wrap = document.querySelector('#view-results .table-wrap');
    const row = document.getElementById('results-scrollbar');
    const slider = document.getElementById('results-scroll-slider');
    const pos = document.getElementById('results-scroll-pos');
    if (!wrap || !row || !slider || !pos) return;

    const maxScroll = Math.max(0, wrap.scrollWidth - wrap.clientWidth);
    if (maxScroll <= 1) {
        row.classList.add('hidden');
        slider.max = '0';
        slider.value = '0';
        pos.textContent = '0%';
        return;
    }

    row.classList.remove('hidden');
    slider.max = String(maxScroll);
    slider.value = String(Math.min(maxScroll, Math.max(0, Math.round(wrap.scrollLeft))));
    const pct = Math.round((Number(slider.value) / maxScroll) * 100);
    pos.textContent = `${pct}%`;
}

function onResultsSliderInput() {
    const wrap = document.querySelector('#view-results .table-wrap');
    const slider = document.getElementById('results-scroll-slider');
    if (!wrap || !slider) return;

    wrap.scrollLeft = Number(slider.value || 0);
    syncResultsScrollSlider();
}

function onResultsTableScroll() {
    syncResultsScrollSlider();
}

async function onResultsCellDoubleClick(e) {
    const cell = e.target.closest('td');
    if (!cell) return;

    const value = String(cell.getAttribute('data-raw') || cell.textContent || '').trim();
    if (!value || value === '—') return;

    try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            await navigator.clipboard.writeText(value);
        } else {
            const t = document.createElement('textarea');
            t.value = value;
            t.style.position = 'fixed';
            t.style.left = '-9999px';
            document.body.appendChild(t);
            t.select();
            document.execCommand('copy');
            t.remove();
        }
        toast('Copied cell value', 'success');
    } catch {
        toast('Copy failed', 'error');
    }
}

function renderLogs(logs) {
    const container = document.getElementById('logs-container');
    if (!container) return;
    
    // Sort logs by timestamp (though they should already be in order)
    const sorted = [...logs].sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
    
    container.innerHTML = sorted.map(log => {
        const time = new Date(log.timestamp).toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
        return `
            <div class="log-entry">
                <span class="log-time">[${time}]</span>
                <span class="log-msg ${esc(log.level || 'info')}">${esc(log.message)}</span>
            </div>
        `;
    }).join('');
    
    // Scroll to bottom
    container.scrollTop = container.scrollHeight;
}

function renderTable(results, emptyMessage = 'No results') {
    const thead = document.getElementById('res-thead');
    const tbody = document.getElementById('res-tbody');
    if (!results.length) {
        thead.innerHTML = '';
        tbody.innerHTML = `<tr><td class="empty-cell" colspan="100">${esc(emptyMessage)}</td></tr>`;
        return;
    }
    const preferredOrder = [
        'company_name',
        'email',
        'phone',
        'website',
        'address',
        'record_score',
        'source_type',
        'source_trust_score',
        'source_url',
        'scraped_at',
    ];
    const seen = new Set();
    const discoveredKeys = [];
    results.forEach((row) => {
        Object.keys(row || {}).forEach((k) => {
            if (!seen.has(k)) {
                seen.add(k);
                discoveredKeys.push(k);
            }
        });
    });
    const keys = [...preferredOrder.filter(k => seen.has(k)), ...discoveredKeys.filter(k => !preferredOrder.includes(k))];
    thead.innerHTML = `<tr>${keys.map(k => `<th>${esc(k)}</th>`).join('')}</tr>`;
    tbody.innerHTML = results.map(row => {
        const isUnstable = row._is_unstable === true;
        const rowClass = isUnstable ? 'unstable-row' : '';
        return `<tr class="${rowClass}">${keys.map(k => {
            let v = row[k];
            if (Array.isArray(v)) v = v.join(', ');
            if (v === null || v === undefined) v = '—';
            const text = String(v);
            const cellClass = (k === '_is_unstable' && isUnstable) ? 'unstable-cell' : '';
            return `<td class="${cellClass}" data-raw="${esc(text)}" title="${esc(text)}">${esc(text)}</td>`;
        }).join('')}</tr>`;
    }).join('');
}

async function recleanCurrentJob() {
    if (!currentJobId) return;
    if (!confirm('Run AI re-clean on this dataset without re-scraping URLs?')) return;

    const btn = document.getElementById('btn-reclean');
    const prev = btn ? btn.innerHTML : '';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner"></span> Re-cleaning...';
    }

    try {
        const res = await fetch(`${API}/api/jobs/${currentJobId}/reclean`, { method: 'POST' });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || 'Re-clean failed');

        toast(`Re-cleaned rows: ${data.before_records || 0} -> ${data.after_records || 0}`, 'success');
        await viewResults(currentJobId);
        await refreshJobs();
    } catch (err) {
        toast(`Re-clean error: ${err.message}`, 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = prev || 'AI Re-clean';
        }
    }
}

function exportCSV() { if (currentJobId) window.open(`${API}/api/jobs/${currentJobId}/export/csv`); }
function exportJSON() { if (currentJobId) window.open(`${API}/api/jobs/${currentJobId}/export/json`); }
function exportExcel() { if (currentJobId) window.open(`${API}/api/jobs/${currentJobId}/export/excel`); }

// ─── Form: Init ───

function initForm() {
    _fieldCounter = 0;
    _filterCounter = 0;
    document.getElementById('inp-name').value = '';
    document.getElementById('inp-intent').value = '';
    document.getElementById('inp-topic').value = '';
    document.getElementById('inp-location').value = '';
    document.getElementById('inp-domain').value = '';
    document.getElementById('inp-origin-location').value = '';
    document.getElementById('inp-max-distance-km').value = '';
    document.getElementById('inp-discover-pages').value = '12';
    document.getElementById('inp-max-per-domain').value = '4';
    document.getElementById('inp-urls').value = '';
    document.getElementById('inp-max-pages').value = '10';
    document.getElementById('inp-min-score').value = '0.35';
    document.getElementById('inp-source-policy').value = 'official_plus_directory';
    document.getElementById('schema-container').innerHTML = '';
    document.getElementById('filters-container').innerHTML = '';
    document.getElementById('discovery-preview').innerHTML = '';
    document.getElementById('discovery-preview').classList.add('hidden');
    const note = document.getElementById('suggestion-note');
    note.textContent = '';
    note.classList.add('hidden');
    setMode('manual');
    addField();
}

// ─── Schema Fields ───

let _fieldCounter = 0;

function addField(preset = null) {
    const c = document.getElementById('schema-container');
    const row = document.createElement('div');
    row.className = 'field-row';
    const p = preset || {};
    const name = esc(p.name || '');
    const desc = esc(p.description || '');
    const selectedType = p.field_type || 'string';
    const fid = _fieldCounter++;
    row.innerHTML = `
        <div class="form-group">
            <label for="sf-name-${fid}">Name</label>
            <input type="text" class="sf-name" id="sf-name-${fid}" placeholder="company_name" value="${name}">
        </div>
        <div class="form-group">
            <label for="sf-type-${fid}">Type</label>
            <select class="sf-type" id="sf-type-${fid}">
                <option value="string" ${selectedType === 'string' ? 'selected' : ''}>Text</option>
                <option value="integer" ${selectedType === 'integer' ? 'selected' : ''}>Integer</option>
                <option value="float" ${selectedType === 'float' ? 'selected' : ''}>Decimal</option>
                <option value="boolean" ${selectedType === 'boolean' ? 'selected' : ''}>Boolean</option>
                <option value="email" ${selectedType === 'email' ? 'selected' : ''}>Email</option>
                <option value="url" ${selectedType === 'url' ? 'selected' : ''}>URL</option>
                <option value="phone" ${selectedType === 'phone' ? 'selected' : ''}>Phone</option>
                <option value="location" ${selectedType === 'location' ? 'selected' : ''}>Location</option>
                <option value="date" ${selectedType === 'date' ? 'selected' : ''}>Date</option>
                <option value="list_string" ${selectedType === 'list_string' ? 'selected' : ''}>List</option>
                <option value="currency" ${selectedType === 'currency' ? 'selected' : ''}>Currency</option>
                <option value="percentage" ${selectedType === 'percentage' ? 'selected' : ''}>Percentage</option>
            </select>
        </div>
        <div class="form-group">
            <label for="sf-desc-${fid}">Hint for AI</label>
            <input type="text" class="sf-desc" id="sf-desc-${fid}" placeholder="e.g. star rating out of 5" value="${desc}">
        </div>
        <button type="button" class="btn-x" onclick="this.parentElement.remove()" aria-label="Remove field">✕</button>
    `;
    c.appendChild(row);
}

async function suggestSchemaFromIntent() {
    const intent = document.getElementById('inp-intent').value.trim();
    if (!intent) {
        toast('Describe your data goal first', 'error');
        return;
    }

    const btn = document.getElementById('btn-suggest-schema');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Suggesting...';

    try {
        const res = await fetch(`${API}/api/schema/suggest`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ intent, max_fields: 8 })
        });
        if (!res.ok) {
            throw new Error((await res.json().catch(() => ({}))).detail || 'Suggestion failed');
        }

        const data = await res.json();
        if (data.topic) document.getElementById('inp-topic').value = data.topic;
        if (data.location) document.getElementById('inp-location').value = data.location;
        if (data.origin_location) document.getElementById('inp-origin-location').value = data.origin_location;
        if (data.max_distance_km !== null && data.max_distance_km !== undefined) {
            document.getElementById('inp-max-distance-km').value = String(data.max_distance_km);
        }

        if (Array.isArray(data.fields) && data.fields.length) {
            const schemaContainer = document.getElementById('schema-container');
            schemaContainer.innerHTML = '';
            data.fields.forEach(f => addField(f));
        }

        const note = document.getElementById('suggestion-note');
        const notes = (data.notes || '').trim();
        if (notes) {
            note.textContent = notes;
            note.classList.remove('hidden');
        } else {
            note.textContent = '';
            note.classList.add('hidden');
        }

        setMode('auto');
        toast('Schema suggestion applied', 'success');
    } catch (err) {
        toast(`Suggestion error: ${err.message}`, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Suggest topic + schema from intent';
    }
}

// ─── Filters ───

let _filterCounter = 0;

function addFilter() {
    const c = document.getElementById('filters-container');
    const fieldOptions = Array.from(document.querySelectorAll('.sf-name'))
        .map(i => i.value).filter(v => v)
        .map(v => `<option value="${esc(v)}">${esc(v)}</option>`).join('');

    const fid = _filterCounter++;
    const row = document.createElement('div');
    row.className = 'filter-row';
    row.innerHTML = `
        <div class="form-group">
            <label for="ff-field-${fid}">Field</label>
            <select class="ff-field" id="ff-field-${fid}">${fieldOptions || '<option value="">—</option>'}</select>
        </div>
        <div class="form-group">
            <label for="ff-op-${fid}">Operator</label>
            <select class="ff-op" id="ff-op-${fid}" onchange="onFilterOpChange(this)">
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
        <button type="button" class="btn-x" onclick="this.parentElement.remove()" aria-label="Remove field">✕</button>
    `;
    c.appendChild(row);
}

function onFilterOpChange(sel) {
    const row = sel.closest('.filter-row');
    const isDistance = sel.value === 'distance_within';

    // Remove existing distance extras
    row.querySelectorAll('.dist-extra').forEach(el => el.remove());

    if (isDistance) {
        row.classList.add('has-distance');
        row.querySelector('.ff-value-group label').textContent = 'Max km/mi';
        // Insert origin and unit fields before the X button
        const xBtn = row.querySelector('.btn-x');
        const distId = _filterCounter;
        const origin = document.createElement('div');
        origin.className = 'form-group dist-extra';
        origin.innerHTML = `<label for="ff-origin-${distId}">Origin address</label><input type="text" class="ff-origin" id="ff-origin-${distId}" placeholder="Los Angeles, CA">`;
        const unit = document.createElement('div');
        unit.className = 'form-group dist-extra';
        unit.innerHTML = `<label for="ff-unit-${distId}">Unit</label><select class="ff-unit" id="ff-unit-${distId}"><option value="km">km</option><option value="miles">miles</option></select>`;
        row.insertBefore(origin, xBtn);
        row.insertBefore(unit, xBtn);
    } else {
        row.classList.remove('has-distance');
        row.querySelector('.ff-value-group label').textContent = 'Value';
    }
}

// ─── Auto-Discovery Preview ───

async function previewDiscovery() {
    const topic = document.getElementById('inp-topic').value.trim();
    if (!topic) { toast('Enter a topic first', 'error'); return; }

    const discoverInput = parseInt(document.getElementById('inp-discover-pages').value, 10);
    const discoverCount = Number.isFinite(discoverInput)
        ? Math.max(1, Math.min(20, discoverInput))
        : 8;
    document.getElementById('inp-discover-pages').value = String(discoverCount);
    const perDomainInput = parseInt(document.getElementById('inp-max-per-domain').value, 10);
    const maxPerDomain = Number.isFinite(perDomainInput)
        ? Math.max(1, Math.min(25, perDomainInput))
        : 4;
    document.getElementById('inp-max-per-domain').value = String(maxPerDomain);

    const preview = document.getElementById('discovery-preview');
    preview.classList.remove('hidden');
    preview.innerHTML = '<div class="disc-loading"><span class="spinner"></span> Discovering URLs...</div>';

    try {
        const res = await fetch(`${API}/api/discover`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                topic,
                location: document.getElementById('inp-location').value.trim(),
                domain: document.getElementById('inp-domain').value.trim(),
                num_results: discoverCount,
                max_per_domain: maxPerDomain,
                source_policy: document.getElementById('inp-source-policy').value || 'official_plus_directory',
                schema_field_names: Array.from(document.querySelectorAll('.sf-name')).map(i => i.value.trim()).filter(Boolean),
                origin_location: document.getElementById('inp-origin-location').value.trim(),
                max_distance_km: (() => {
                    const n = parseFloat(document.getElementById('inp-max-distance-km').value);
                    return Number.isFinite(n) ? n : null;
                })()
            })
        });

        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || 'Discovery failed');
        if (!data.urls.length) {
            preview.innerHTML = '<div class="disc-loading">No URLs found. Try a different topic.</div>';
            return;
        }

        preview.innerHTML = data.urls.map(u => `
            <div class="disc-item">
                <div class="disc-url">${esc(u.url || '')}</div>
                <div class="disc-reason">${esc(u.title || '')} — ${esc(u.reason || '')}</div>
            </div>
        `).join('');

    } catch (e) {
        preview.innerHTML = `<div class="disc-loading">Discovery error: ${esc(e.message || 'Unknown error')}</div>`;
    }
}

// ─── Submit Job ───

async function submitJob(e) {
    e.preventDefault();

    const name = document.getElementById('inp-name').value.trim();
    if (!name) { toast('Enter a job name', 'error'); return; }

    // Schema
    const schema = [];
    document.querySelectorAll('.field-row').forEach(row => {
        const n = row.querySelector('.sf-name').value.trim();
        if (n) schema.push({
            name: n,
            field_type: row.querySelector('.sf-type').value,
            description: row.querySelector('.sf-desc').value.trim(),
            required: true
        });
    });
    if (!schema.length) { toast('Add at least one schema field', 'error'); return; }

    // Filters
    const filters = [];
    document.querySelectorAll('.filter-row').forEach(row => {
        const f = row.querySelector('.ff-field').value;
        const op = row.querySelector('.ff-op').value;
        const val = row.querySelector('.ff-value')?.value.trim() || '';
        if (f) {
            const filter = { field_name: f, operator: op, value: val };
            if (op === 'distance_within') {
                filter.origin_address = row.querySelector('.ff-origin')?.value.trim() || '';
                filter.distance_unit = row.querySelector('.ff-unit')?.value || 'km';
            }
            filters.push(filter);
        }
    });

    // URLs or topic
    let urls = [];
    let topic = '', location = '', domain = '';
    const sourcePolicy = document.getElementById('inp-source-policy').value || 'official_plus_directory';
    const intent = document.getElementById('inp-intent').value.trim();
    const originLocation = document.getElementById('inp-origin-location').value.trim();
    const maxDistanceRaw = parseFloat(document.getElementById('inp-max-distance-km').value);
    const maxDistance = Number.isFinite(maxDistanceRaw) ? maxDistanceRaw : null;
    const minScoreRaw = parseFloat(document.getElementById('inp-min-score').value);
    const minScore = Number.isFinite(minScoreRaw) ? Math.max(0, Math.min(1, minScoreRaw)) : 0.35;
    const perDomainInput = parseInt(document.getElementById('inp-max-per-domain').value, 10);
    const maxPerDomain = Number.isFinite(perDomainInput)
        ? Math.max(1, Math.min(25, perDomainInput))
        : 4;
    document.getElementById('inp-max-per-domain').value = String(maxPerDomain);
    let maxPages = parseInt(document.getElementById('inp-max-pages').value, 10) || 10;

    if (currentMode === 'manual') {
        urls = document.getElementById('inp-urls').value.split('\n').map(u => u.trim()).filter(u => u);
        if (!urls.length) { toast('Enter at least one URL', 'error'); return; }
    } else {
        topic = document.getElementById('inp-topic').value.trim();
        location = document.getElementById('inp-location').value.trim();
        domain = document.getElementById('inp-domain').value.trim();
        const discoverInput = parseInt(document.getElementById('inp-discover-pages').value, 10);
        maxPages = Number.isFinite(discoverInput)
            ? Math.max(1, Math.min(20, discoverInput))
            : maxPages;
        document.getElementById('inp-discover-pages').value = String(maxPages);
        if (!topic) { toast('Enter a topic', 'error'); return; }
    }

    const payload = {
        name, mode: currentMode, intent, urls, topic, location, preferred_domain: domain,
        origin_location: originLocation,
        max_distance_km: maxDistance,
        source_policy: sourcePolicy,
        max_per_domain: maxPerDomain,
        schema_fields: schema, filters,
        deduplicate: document.getElementById('chk-dedup').checked,
        deduplicate_field: document.getElementById('inp-dedup-field').value.trim(),
        pagination: document.getElementById('chk-pagination').checked,
        max_pages: maxPages,
        min_record_score: minScore,
    };

    const btn = document.getElementById('btn-submit');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Starting...';

    try {
        const res = await fetch(`${API}/api/jobs`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Failed');
        const data = await res.json();
        toast(`Job started`, 'success');
        switchView('jobs');
        refreshJobs();
    } catch (err) {
        toast(`Error: ${err.message}`, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = 'Start Scraping →';
    }
}

// ─── Utils ───

function esc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

// ─── Cognition State ───

async function refreshCognition() {
    try {
        const res = await fetch(`${API}/api/system/topology`);
        if (!res.ok) throw new Error('Topology unavailable');
        const data = await res.json();

        const metrics = data.metrics || {};
        document.getElementById('kpi-pressure').textContent = (metrics.field_pressure || 0).toFixed(3);
        document.getElementById('kpi-integrity').textContent = (metrics.integrity_score || 0).toFixed(3);
        document.getElementById('kpi-energy').textContent = (metrics.global_energy || 0).toFixed(3);
        document.getElementById('kpi-exclusions').textContent = metrics.exclusion_count || 0;
        document.getElementById('kpi-basins').textContent = Array.isArray(data.field_regions) ? data.field_regions.length : 0;

        const communities = data.global_communities || [];
        const commList = document.getElementById('community-list');
        if (!communities.length) {
            commList.innerHTML = '<div class="empty"><p>No stable communities identified</p></div>';
        } else {
            commList.innerHTML = communities.map(c => `
                <div style="padding: 0.75rem; border-bottom: 1px solid var(--border);">
                    <div style="display:flex; flex-wrap:wrap; gap:0.4rem;">
                        ${c.map(role => `<span class="mode-tag">${esc(role)}</span>`).join('')}
                    </div>
                </div>
            `).join('');
        }

        const patterns = data.schema_patterns || [];
        const patternList = document.getElementById('schema-pattern-list');
        if (!patterns.length) {
            patternList.innerHTML = '<div class="empty"><p>No recurring schemas learned yet</p></div>';
        } else {
            patternList.innerHTML = patterns.sort((a,b) => b.count - a.count).map(p => `
                <div style="padding: 0.75rem; border-bottom: 1px solid var(--border);">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <div style="display:flex; flex-wrap:wrap; gap:0.4rem;">
                            ${p.roles.map(role => `<span class="mode-tag">${esc(role)}</span>`).join('')}
                        </div>
                        <span style="color:var(--text-muted); font-size:0.85rem;">Count: ${p.count}</span>
                    </div>
                </div>
            `).join('');
        }

        const exclusions = data.learned_exclusions || [];
        const excList = document.getElementById('exclusion-list');
        if (!exclusions.length) {
            excList.innerHTML = '<div class="empty"><p>No exclusions learned yet</p></div>';
        } else {
            excList.innerHTML = exclusions.sort((a,b) => b.strength - a.strength).map(e => `
                <div style="display:flex; justify-content:space-between; padding: 0.5rem; border-bottom: 1px solid var(--border);">
                    <span style="font-weight:600; color:var(--text-main);">${esc(e.roles.join(' ↔ '))}</span>
                    <span style="color:var(--text-muted);">Strength: ${e.strength.toFixed(3)}</span>
                </div>
            `).join('');
        }

        const compats = data.role_compatibility || [];
        const simList = document.getElementById('role-similarity-list');
        if (!compats.length) {
            simList.innerHTML = '<div class="empty"><p>Manifold is cold</p></div>';
        } else {
            // Filter for high compatibility scores
            simList.innerHTML = compats.filter(c => c.score > 0.7).sort((a,b) => b.score - a.score).map(c => `
                <div style="display:flex; justify-content:space-between; padding: 0.5rem; border-bottom: 1px solid var(--border);">
                    <span style="font-weight:600; color:var(--text-main);">${esc(c.role)} <span style="color:var(--text-muted); font-weight:400;">≈</span> ${esc(c.type)}</span>
                    <span style="color:var(--text-muted);">Score: ${c.score.toFixed(3)}</span>
                </div>
            `).join('');
        }

        const basins = data.field_regions || [];
        const basinList = document.getElementById('basin-list');
        if (!basins.length) {
            basinList.innerHTML = '<div class="empty"><p>No active conflict basins</p></div>';
        } else {
            basinList.innerHTML = basins.sort((a,b) => b.instability - a.instability).map(b => `
                <div style="padding: 0.5rem; border-bottom: 1px solid var(--border);">
                    <div style="font-weight:600; color:var(--text-main); margin-bottom:0.25rem;">Token: "${esc(b.token)}"</div>
                    <div style="font-size:0.85rem; color:var(--text-muted); margin-bottom:0.25rem;">Clash: ${esc(b.competing_roles.join(', '))}</div>
                    <div style="font-size:0.85rem; color:var(--text-muted); display:flex; gap:1rem;">
                        <span>Instability: ${b.instability.toFixed(3)}</span>
                        <span>Energy: ${b.local_energy.toFixed(3)}</span>
                    </div>
                </div>
            `).join('');
        }
    } catch (e) {
        toast(`Failed to load cognition state: ${e.message}`, 'error');
    }
}

// ─── Init ───
document.addEventListener('DOMContentLoaded', () => {
    const uiState = readUIState();

    const jobsSearch = document.getElementById('jobs-search');
    if (jobsSearch && typeof uiState.jobsSearch === 'string') {
        jobsSearch.value = uiState.jobsSearch;
    }
    if (jobsSearch) jobsSearch.addEventListener('input', onJobsFilterChanged);

    const jobsStatus = document.getElementById('jobs-status-filter');
    if (jobsStatus && typeof uiState.jobsStatus === 'string') {
        jobsStatus.value = uiState.jobsStatus;
    }
    if (jobsStatus) jobsStatus.addEventListener('change', onJobsFilterChanged);

    const resultSearch = document.getElementById('inp-result-search');
    if (resultSearch) resultSearch.addEventListener('input', renderFilteredResults);

    const resultsSlider = document.getElementById('results-scroll-slider');
    if (resultsSlider) resultsSlider.addEventListener('input', onResultsSliderInput);

    const tableWrap = document.querySelector('#view-results .table-wrap');
    if (tableWrap) tableWrap.addEventListener('scroll', onResultsTableScroll);

    const resultBody = document.getElementById('res-tbody');
    if (resultBody) resultBody.addEventListener('dblclick', onResultsCellDoubleClick);

    document.addEventListener('keydown', onGlobalKeydown);
    window.addEventListener('focus', () => {
        refreshSystemStatus();
        refreshJobs();
        updateJobsLastUpdatedLabel();
    });
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) {
            refreshSystemStatus();
            refreshJobs();
            updateJobsLastUpdatedLabel();
        }
    });

    refreshSystemStatus();
    window.addEventListener('resize', syncResultsScrollSlider);

    const initialView = ['jobs', 'new', 'recycle', 'cognition'].includes(String(uiState.view || ''))
        ? String(uiState.view)
        : 'jobs';
    switchView(initialView);
    refreshJobs();
    const refreshInterval = (typeof window.DATAFORGE_REFRESH_INTERVAL === 'number') ? window.DATAFORGE_REFRESH_INTERVAL : 10000;
    const statusInterval = (typeof window.DATAFORGE_STATUS_INTERVAL === 'number') ? window.DATAFORGE_STATUS_INTERVAL : 10000;
    setInterval(() => {
        refreshJobs();
        updateJobsLastUpdatedLabel();
    }, refreshInterval);
    statusTimer = setInterval(refreshSystemStatus, statusInterval);
});
