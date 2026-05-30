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

export function showApiKeyPrompt() {
    const current = getApiKey();
    const key = prompt('Enter your DataForge API key:', current);
    if (key !== null) {
        setApiKey(key.trim());
        if (key.trim()) {
            toast('API key set', 'success');
            // These are imported dynamically to avoid circular deps
            import('./jobs.js').then(m => { m.refreshSystemStatus(); m.refreshJobs(); });
        }
    }
}

export function showAdminKeyPrompt() {
    const key = prompt('Enter your DataForge Admin key (for this session only):');
    if (key !== null) {
        setAdminKey(key.trim());
        if (key.trim()) {
            toast('Admin key set for this session', 'success');
        }
    }
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
            if (now - lastApi403 > 15000) {
                lastApi403 = now;
                showApiKeyPrompt();
            }
        }
        return res;
    } catch (err) {
        throw err;
    }
}
