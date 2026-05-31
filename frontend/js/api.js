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

// ─── API Key Management ───

function getApiKey() {
    try { return sessionStorage.getItem('dataforge_api_key') || ''; } catch { return ''; }
}

function setApiKey(key) {
    try { sessionStorage.setItem('dataforge_api_key', key); } catch { /* ignore storage errors */ }
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
        desc.textContent = 'Enter your DataForge Admin key for protected actions (session only).';
    } else {
        title.textContent = '\u{1F511} API Key';
        desc.textContent = 'Enter your DataForge API key for production access.';
        try { input.value = sessionStorage.getItem('dataforge_api_key') || ''; } catch { /* ignore */ }
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

export { getApiKey, isKeyModalVisible, closeKeyModal, saveKeyFromModal };
