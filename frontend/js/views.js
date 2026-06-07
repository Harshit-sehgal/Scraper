/* ═══════════════════════════════════════════
   DataForge — View Management
   ═══════════════════════════════════════════ */

import { writeUIState, isTypingTarget, showShortcuts, hideShortcuts, isShortcutsVisible, closeConfirm, isConfirmVisible } from './utils.js';

export let currentView = 'jobs';
export let currentMode = 'manual';

export function setCurrentView(name) {
    currentView = name;
}

export function setCurrentMode(mode) {
    currentMode = mode;
}

// ─── View / Tab Switching ───

export function switchView(name) {
    currentView = name;
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    document.querySelectorAll('.tab').forEach(t => {
        t.classList.remove('active');
        t.setAttribute('aria-selected', 'false');
    });
    document.getElementById(`view-${name}`).classList.add('active');

    const tabMap = { jobs: 'tab-jobs', new: 'tab-new', recycle: 'tab-recycle', cognition: 'tab-cognition', dashboard: 'tab-dashboard' };
    const tabEl = document.getElementById(tabMap[name]);
    if (tabEl) {
        tabEl.classList.add('active');
        tabEl.setAttribute('aria-selected', 'true');
    }

    if (name === 'jobs') import('./jobs.js').then(m => m.refreshJobs()).catch(() => {});
    if (name === 'new') import('./form.js').then(m => m.initForm()).catch(() => {});
    if (name === 'recycle') import('./recycle.js').then(m => m.refreshRecycleBin()).catch(() => {});
    if (name === 'cognition') import('./cognition.js').then(m => m.refreshCognition()).catch(() => {});
    if (name === 'dashboard') import('./dashboard.js').then(m => m.refreshDashboard()).catch(() => {});

    writeUIState({ view: name });
}

// ─── Mode Toggle ───

export function setMode(mode) {
    currentMode = mode;
    document.querySelectorAll('#mode-toggle .toggle').forEach(t => {
        t.classList.toggle('active', t.dataset.mode === mode);
    });
    document.getElementById('section-manual').classList.toggle('hidden', mode !== 'manual');
    document.getElementById('section-auto').classList.toggle('hidden', mode !== 'auto');
}

// ─── Global Keyboard Handler ───

const TAB_KEYS = {
    '1': 'jobs',
    '2': 'new',
    '3': 'recycle',
    '4': 'cognition',
    '5': 'dashboard',
};

export function onGlobalKeydown(e) {
    const typing = isTypingTarget(e.target);
    const jobsSearch = document.getElementById('jobs-search');
    const resultSearch = document.getElementById('inp-result-search');

    // Number keys 1-5: switch between tabs (only when not typing)
    if (!typing && e.key >= '1' && e.key <= '5') {
        e.preventDefault();
        const viewName = TAB_KEYS[e.key];
        if (viewName) {
            switchView(viewName);
        }
        return;
    }

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
        // Close confirmation modal if open
        if (isConfirmVisible()) {
            closeConfirm();
            e.preventDefault();
            return;
        }

        // Close shortcuts modal if open
        if (isShortcutsVisible()) {
            hideShortcuts();
            e.preventDefault();
            return;
        }

        if (document.activeElement === jobsSearch && jobsSearch?.value) {
            jobsSearch.value = '';
            import('./jobs.js').then(m => m.onJobsFilterChanged()).catch(() => {});
            e.preventDefault();
            return;
        }

        if (document.activeElement === resultSearch && resultSearch?.value) {
            resultSearch.value = '';
            import('./results.js').then(m => m.renderFilteredResults()).catch(() => {});
            e.preventDefault();
        }
    }

    if (!typing && e.key === '?') {
        e.preventDefault();
        showShortcuts();
    }
}
