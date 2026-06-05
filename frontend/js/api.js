/* ═══════════════════════════════════════════
   DataForge — API Layer
   ═══════════════════════════════════════════ */

import { toast } from './utils.js';

// ─── API Base URL ───

export const API = (() => {
    const explicit = typeof window.DATAFORGE_API_BASE === 'string' ? window.DATAFORGE_API_BASE.trim() : '';
    if (explicit) return explicit.replace(/\/$/, '');

    const { protocol, hostname, port, origin } = window.location;
    if (protocol === 'http:' || protocol === 'https:') {
        if ((hostname === 'localhost' || hostname === '127.0.0.1') && ['3000', '5173'].includes(port)) {
            return 'http://127.0.0.1:8000';
        }
        return origin;
    }
    return 'http://127.0.0.1:8000';
})();

// ─── API Key Management ────────────────────────────────────────────────────
// SECURITY: The API key is held ONLY in JavaScript memory for the lifetime
// of the current page. It is NEVER persisted to sessionStorage, localStorage,
// or any other durable browser storage. A page reload will require the user
// to re-enter the key. This protects the key from any same-origin XSS that
// succeeds in exfiltrating storage but is not running in this page's context.
//
// Future hardening: replace this with a backend-issued, HTTP-only,
// Secure, SameSite=strict session cookie minted by /api/session after
// validating X-API-Key. That removes the need for browser-side key
// storage entirely.
let _apiKey = '';

function getApiKey() {
    return _apiKey;
}

function setApiKey(key) {
    _apiKey = (key || '').trim();
}

function clearApiKey() {
    _apiKey = '';
}

// ─── Admin Key Management (session-scoped) ─

let _adminKey = '';

export function getAdminKey() {
    return _adminKey;
}

export function setAdminKey(key) {
    _adminKey = key;
}

// ─── Modal Key Management ───

let _pendingKeyType = null; // 'api' | 'admin'

function setupKeyModal(type) {
    const overlay = document.getElementById('apikey-overlay');
    const input = document.getElementById('apikey-input');
    const title = document.getElementById('apikey-modal-title');
    const desc = document.getElementById('apikey-modal-desc');
    const error = document.getElementById('apikey-error');

    if (!overlay || !input || !title || !desc || !error) return;

    error.classList.add('hidden');
    input.value = '';

    if (type === 'admin') {
        title.textContent = '\u{1F6E1}\uFE0F Admin Key';
        desc.textContent = 'Enter your DataForge Admin key for protected actions (session only — held in memory, not stored).';
    } else {
        title.textContent = '\u{1F511} API Key';
        desc.textContent = 'Enter your DataForge API key. The key is held in memory only and is cleared on page reload.';
        // Pre-fill only with the in-memory copy; never read from storage.
        input.value = getApiKey() || '';
    }

    _pendingKeyType = type;
    overlay.classList.remove('hidden');
    setTimeout(() => input.focus(), 100);
}

function closeKeyModal() {
    const overlay = document.getElementById('apikey-overlay');
    if (overlay) overlay.classList.add('hidden');
    _pendingKeyType = null;
}

function saveKeyFromModal() {
    if (!_pendingKeyType) return;

    const input = document.getElementById('apikey-input');
    const error = document.getElementById('apikey-error');
    if (!input || !error) return;

    const key = input.value.trim();

    if (!key) {
        error.textContent = 'Please enter a key or click Cancel.';
        error.classList.remove('hidden');
        return;
    }

    if (_pendingKeyType === 'admin') {
        setAdminKey(key);
        toast('Admin key set for this session', 'success');
    } else {
        setApiKey(key);
        toast('API key set', 'success');
        import('./jobs.js').then(m => { m.refreshSystemStatus(); m.refreshJobs(); });
    }

    closeKeyModal();
}

export function showApiKeyPrompt() {
    setupKeyModal('api');
}

export function showAdminKeyPrompt() {
    setupKeyModal('admin');
}

function isKeyModalVisible() {
    const overlay = document.getElementById('apikey-overlay');
    return overlay && !overlay.classList.contains('hidden');
}

// ─── 403 Throttle ───

let lastApi403 = 0;

// ─── Central Fetch Wrapper ───

export async function apiFetch(url, options = {}) {
    const { admin, ...rest } = options;
    const headers = { ...(rest.headers || {}) };
    const key = getApiKey();
    if (key && (url.startsWith(API + '/api/') || url.startsWith('/api/'))) {
        headers['X-API-Key'] = key;
    }
    if (admin) {
        const adminKey = getAdminKey();
        if (adminKey) {
            headers['X-Admin-Key'] = adminKey;
        }
    }
    try {
        const res = await fetch(url, { ...rest, headers });
        if (res.status === 403 && !admin) {
            const now = Date.now();
            if (now - lastApi403 > 15000 && !isKeyModalVisible()) {
                lastApi403 = now;
                showApiKeyPrompt();
            }
        }
        return res;
    } catch (err) {
        throw err;
    }
}

export { getApiKey, isKeyModalVisible, closeKeyModal, saveKeyFromModal, clearApiKey };
