/* ═══════════════════════════════════════════
   DataForge — Utility Functions
   ═══════════════════════════════════════════ */

// ─── HTML Escaping ───

export function esc(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

// Safer escaping for JavaScript string contexts (onclick handlers).
// HTML-escapes AND escapes characters that could break out of JS strings:
//   ' (single quote), " (double quote), \ (backslash), \n (newline), \r (carriage return)
export function jsStr(s) {
    if (typeof s !== 'string') s = String(s || '');
    return s
        .replace(/\\/g, '\\\\')
        .replace(/'/g, "\\'")
        .replace(/"/g, '\\"')
        .replace(/\n/g, '\\n')
        .replace(/\r/g, '\\r');
}

// ─── Toast Notifications ───

export function toast(msg, type = 'info') {
    const c = document.getElementById('toasts');
    const t = document.createElement('div');
    t.className = `toast ${type}`;
    t.textContent = msg;
    c.appendChild(t);
    setTimeout(() => t.remove(), 4000);
}

// ─── Engine Status ───

export function setEngineStatus(text, offline = false) {
    const el = document.getElementById('engine-status');
    const textEl = document.getElementById('engine-status-text');
    if (!el || !textEl) return;
    textEl.textContent = text;
    el.classList.toggle('offline', offline);
}

// ─── UI State Persistence ───

const UI_STATE_KEY = 'dataforge_ui_state_v1';

export function readUIState() {
    try {
        const raw = localStorage.getItem(UI_STATE_KEY);
        return raw ? JSON.parse(raw) : {};
    } catch {
        return {};
    }
}

export function writeUIState(patch) {
    try {
        const next = { ...readUIState(), ...(patch || {}) };
        localStorage.setItem(UI_STATE_KEY, JSON.stringify(next));
    } catch {
        // Ignore storage errors (private mode, quota, etc.)
    }
}

// ─── Jobs Last Updated Label ───

let jobsUpdatedAt = 0;

export function getJobsUpdatedAt() {
    return jobsUpdatedAt;
}

export function setJobsUpdatedAt(ts) {
    jobsUpdatedAt = ts;
}

export function updateJobsLastUpdatedLabel(forceText = '') {
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

// ─── Keyboard Helpers ───

export function isTypingTarget(target) {
    if (!target) return false;
    const tag = String(target.tagName || '').toLowerCase();
    return tag === 'input' || tag === 'textarea' || tag === 'select' || target.isContentEditable;
}
