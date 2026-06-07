/* ═══════════════════════════════════════════
   DataForge — Frontend App Entry Point (ES Module)
   ═══════════════════════════════════════════
   Re-exports all public APIs and initializes the app.
   ═══════════════════════════════════════════ */

// ─── Re-export public APIs for debugging / devtools ───
export * from './js/utils.js';
export * from './js/api.js';
export * from './js/views.js';
export * from './js/jobs.js';
export * from './js/recycle.js';
export * from './js/results.js';
export * from './js/analyzer.js';
export * from './js/form.js';
export * from './js/cognition.js';
export * from './js/dashboard.js';

// ─── Init ───
import { readUIState, updateJobsLastUpdatedLabel, initTheme, toggleTheme, showShortcuts, hideShortcuts, setEnginePolling, closeConfirm, executeConfirm } from './js/utils.js';
import { refreshSystemStatus, refreshJobs, refreshJobsManual, onJobsFilterChanged } from './js/jobs.js';
import { onGlobalKeydown, switchView } from './js/views.js';
import { onResultsSliderInput, onResultsTableScroll, onResultsCellDoubleClick, renderFilteredResults } from './js/results.js';
import { analyzeURL, toggleAllFields, applyAnalyzedFields, clearAnalysis } from './js/analyzer.js';
import { initForm, addField, addFilter, suggestSchemaFromIntent, previewDiscovery, onFilterOpChange, submitJob } from './js/form.js';
import { refreshCognition } from './js/cognition.js';
import { refreshDashboard, switchOperatorMode } from './js/dashboard.js';
import { refreshRecycleBin, restoreJob, hardDeleteJob, clearRecycleBin } from './js/recycle.js';
import { cancelJob, deleteJob, clearTerminalJobs } from './js/jobs.js';
import { viewResults, recleanCurrentJob, exportCSV, exportJSON, exportExcel } from './js/results.js';
import { showApiKeyPrompt, showAdminKeyPrompt, closeKeyModal, saveKeyFromModal, isKeyModalVisible } from './js/api.js';
import { setMode } from './js/views.js';

document.addEventListener('DOMContentLoaded', async () => {
    const uiState = readUIState();

    // Restore search/status filters
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

    // URL Analyzer: Enter key triggers analysis. The handler also
    // checks the analyze button's disabled state so a fast double
    // press of Enter — which would otherwise bypass the button
    // debounce and fire two parallel API calls — is ignored while
    // the first request is in flight.
    const analyzeUrlInput = document.getElementById('inp-analyze-url');
    if (analyzeUrlInput) {
        analyzeUrlInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                const analyzeBtn = document.getElementById('btn-analyze-url');
                if (analyzeBtn && analyzeBtn.disabled) return;
                analyzeURL();
            }
        });
    }

    // ── API Key Modal: Enter saves, Escape cancels ──
    const apikeyInput = document.getElementById('apikey-input');
    if (apikeyInput) {
        apikeyInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                saveKeyFromModal();
            }
            if (e.key === 'Escape') {
                e.preventDefault();
                closeKeyModal();
            }
        });
    }

    // ── API Key Toggle Visibility ──
    const apikeyToggle = document.getElementById('apikey-toggle-vis');
    if (apikeyToggle) {
        apikeyToggle.addEventListener('change', () => {
            const input = document.getElementById('apikey-input');
            if (input) input.type = apikeyToggle.checked ? 'text' : 'password';
        });
    }

    // ── Global keyboard ──
    document.addEventListener('keydown', onGlobalKeydown);

    // ── Window focus / visibility ──
    // Tab-switching in modern browsers fires a flurry of
    // ``visibilitychange`` and ``focus`` events when the user
    // hovers over the tab strip or alt-tabs. Each of those events
    // would otherwise kick off three API calls, so we coalesce
    // them with a one-shot timer. The latest event wins; earlier
    // ones are dropped before they reach the network.
    let _focusRefreshTimer = null;
    const _scheduleFocusRefresh = () => {
        if (_focusRefreshTimer) return;
        _focusRefreshTimer = setTimeout(() => {
            _focusRefreshTimer = null;
            refreshSystemStatus();
            refreshJobs();
            updateJobsLastUpdatedLabel();
        }, 250);
    };
    window.addEventListener('focus', _scheduleFocusRefresh);
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) {
            _scheduleFocusRefresh();
        }
    });

    // ── Resize ──
    // The horizontal scroll-snap slider needs to recompute its range
    // when the viewport changes width. ResizeObserver is a no-op for
    // window, so we hook the event directly and call the exported
    // ``syncResultsScrollSlider`` from results.js. We do not dispatch a
    // synthetic ``scroll`` event on the table wrap — that would mix input
    // and resize handling and could fire onResultsTableScroll() with a
    // stale state.
    import('./js/results.js').then(({ syncResultsScrollSlider }) => {
        window.addEventListener('resize', () => syncResultsScrollSlider());
    });

    // ── Init theme ──
    initTheme();

    // ── Initial view ──
    const initialView = ['jobs', 'new', 'recycle', 'cognition', 'dashboard'].includes(String(uiState.view || ''))
        ? String(uiState.view)
        : 'jobs';
    switchView(initialView);
    refreshJobs();

    // ── Polling intervals ──
    const refreshInterval = (typeof window.DATAFORGE_REFRESH_INTERVAL === 'number') ? window.DATAFORGE_REFRESH_INTERVAL : 10000;
    const statusInterval = (typeof window.DATAFORGE_STATUS_INTERVAL === 'number') ? window.DATAFORGE_STATUS_INTERVAL : 10000;
    setInterval(() => {
        setEnginePolling(true);
        Promise.resolve(refreshJobs()).catch(() => setEnginePolling(false));
        updateJobsLastUpdatedLabel();
    }, refreshInterval);
    setInterval(refreshSystemStatus, statusInterval);

    // Engine connection check
    window.addEventListener('online', () => setEnginePolling(true));
    window.addEventListener('offline', () => setEnginePolling(false));

    // Dashboard polling (every 30s)
    setInterval(() => {
        const { currentView } = window.__DATAFORGE_VIEW || {};
        if (currentView === 'dashboard') refreshDashboard();
    }, 30000);

    // ── Central event delegation for all data-action elements ──
    document.addEventListener('click', (e) => {
        const btn = e.target.closest('[data-action]');
        if (!btn) return;

        const action = btn.getAttribute('data-action');
        const id = btn.getAttribute('data-id') || '';
        const mode = btn.getAttribute('data-mode') || '';
        const view = btn.getAttribute('data-view') || '';

        switch (action) {
            case 'view-results':              if (id) viewResults(id); break;
            case 'cancel-job':                if (id) cancelJob(id); break;
            case 'delete-job':                if (id) deleteJob(id); break;
            case 'restore-job':               if (id) restoreJob(id); break;
            case 'hard-delete-job':           if (id) hardDeleteJob(id); break;
            case 'remove-field':              btn.closest('.field-row')?.remove(); break;
            case 'remove-filter':             btn.closest('.filter-row')?.remove(); break;
            case 'toggle-field': {
                const index = btn.getAttribute('data-index');
                if (index !== null) {
                    const items = document.querySelectorAll('.analyze-field-item');
                    const checkboxes = document.querySelectorAll('.analyze-field-checkbox');
                    const idx = parseInt(index, 10);
                    if (!isNaN(idx) && checkboxes[idx]) {
                        checkboxes[idx].checked = !checkboxes[idx].checked;
                        if (items[idx]) items[idx].classList.toggle('selected', checkboxes[idx].checked);
                    }
                }
                break;
            }
            case 'toast-info': {
                const msg = btn.getAttribute('data-message');
                if (msg) import('./js/utils.js').then(m => m.toast(msg, 'info'));
                break;
            }
            case 'save-apikey':               saveKeyFromModal(); break;
            case 'close-apikey':               closeKeyModal(); break;
            case 'show-api-key':              showApiKeyPrompt(); break;
            case 'show-admin-key':            showAdminKeyPrompt(); break;
            case 'switch-view':               if (view) switchView(view); break;
            case 'clear-terminal-jobs':       clearTerminalJobs(); break;
            case 'refresh-jobs':              refreshJobsManual(); break;
            case 'clear-recycle-bin':         clearRecycleBin(); break;
            case 'refresh-dashboard':         refreshDashboard(); break;
            case 'switch-operator-mode':      if (mode) switchOperatorMode(mode); break;
            case 'analyze-url':               analyzeURL(); break;
            case 'toggle-all-fields':         toggleAllFields(btn.getAttribute('data-select') === 'true'); break;
            case 'apply-fields':              applyAnalyzedFields(); break;
            case 'clear-analysis':            clearAnalysis(); break;
            case 'set-mode':                  if (mode) setMode(mode); break;
            case 'suggest-schema':            suggestSchemaFromIntent(); break;
            case 'preview-discovery':         previewDiscovery(); break;
            case 'add-field':                 addField(); break;
            case 'add-filter':                addFilter(); break;

            case 'reclean-job':               recleanCurrentJob(); break;
            case 'export-csv':                exportCSV(); break;
            case 'export-json':               exportJSON(); break;
            case 'export-excel':              exportExcel(); break;
            case 'toggle-theme':              toggleTheme(); break;
            case 'show-shortcuts':             showShortcuts(); break;
            case 'close-shortcuts':            hideShortcuts(); break;
            case 'close-confirm':               closeConfirm(); break;
            case 'confirm-action':              executeConfirm(); break;
            case 'copy-job-id':                 if (id) navigator.clipboard?.writeText(id).then(() => {
                                                    btn.textContent = '✓';
                                                    btn.classList.add('copied');
                                                    setTimeout(() => { btn.textContent = '📋'; btn.classList.remove('copied'); }, 2000);
                                                }).catch(() => {}); break;
            case 'refresh-cognition':          refreshCognition(); break;
            case 'toggle-field-item': {
                // If the user clicked the checkbox itself, the change handler
                // below will already have toggled the `selected` class. Skip
                // here to avoid double-toggling (which would silently undo the
                // user's click).
                if (e.target.matches('.analyze-field-checkbox')) {
                    break;
                }
                const checkbox = btn.querySelector('.analyze-field-checkbox');
                if (checkbox) {
                    checkbox.checked = !checkbox.checked;
                    btn.classList.toggle('selected', checkbox.checked);
                }
                break;
            }
        }
        e.stopPropagation();
    });

    // ── Delegated change handler for filter operation select ──
    document.addEventListener('change', (e) => {
        const sel = e.target.closest('.ff-op');
        if (sel) {
            onFilterOpChange(sel);
        }

        const checkbox = e.target.closest('.analyze-field-checkbox');
        if (checkbox) {
            const item = checkbox.closest('.analyze-field-item');
            if (item) item.classList.toggle('selected', checkbox.checked);
        }
    });

    // ── Job form submit ──
    const jobForm = document.getElementById('job-form');
    if (jobForm) {
        jobForm.addEventListener('submit', submitJob);
    }

    // Expose currentView for dashboard polling via a getter
    window.__DATAFORGE_VIEW = {};
    const viewsMod = await import('./js/views.js');
    Object.defineProperty(window.__DATAFORGE_VIEW, 'currentView', {
        get: () => viewsMod.currentView,
        enumerable: true
    });
});
