/* ═══════════════════════════════════════════
   DataForge — API Layer
   ═══════════════════════════════════════════ */

import { toast, attachFocusTrapTo, detachFocusTrapFrom } from "./utils.js";
import { refreshSystemStatus, refreshJobs } from "./jobs.js";

// ─── API Base URL ───

export const API = (() => {
  const explicit = typeof window.DATAFORGE_API_BASE === "string" ? window.DATAFORGE_API_BASE.trim() : "";
  if (explicit) return explicit.replace(/\/$/, "");

  const { protocol, hostname, port, origin } = window.location;
  if (protocol === "http:" || protocol === "https:") {
    if ((hostname === "localhost" || hostname === "127.0.0.1") && ["3000", "5173"].includes(port)) {
      return "http://127.0.0.1:8000";
    }
    return origin;
  }
  return "http://127.0.0.1:8000";
})();

// ─── Session-based Auth ──────────────────────────────────────────────────
// G2: Browser clients now authenticate via an HTTP-only session cookie.
// On app load we try GET /api/session/me — if the cookie is valid the
// app authenticates silently. If not, the user enters an API key which
// is exchanged for a session cookie via POST /api/session (the raw key
// is never stored in JS memory beyond the exchange call).
//
// The session cookie is HTTP-only, SameSite=strict, and (in production)
// Secure.  It is automatically sent by the browser on every fetch() to
// the same origin, so we no longer need to attach X-API-Key headers.
//
// Direct API key auth via X-API-Key header is still supported for
// non-browser clients (curl, scripts, integrations).

let _sessionChecked = false;
let _isSessionAuthenticated = false;
let _sessionRole = "";

// ─── Legacy API Key Management (kept for backward compat and
//      non-browser / programmatic usage) ───────────────────────────────
// SECURITY: The API key is held ONLY in JavaScript memory for the lifetime
// of the current page. It is NEVER persisted to sessionStorage, localStorage,
// or any other durable browser storage. A page reload will require the user
// to re-enter the key. This protects the key from any same-origin XSS that
// succeeds in exfilitrating storage but is not running in this page's context.
let _apiKey = "";

function getApiKey() {
  return _apiKey;
}

function setApiKey(key) {
  _apiKey = (key || "").trim();
}

function clearApiKey() {
  _apiKey = "";
}

// ─── Admin Key Management (session-scoped) ─

let _adminKey = "";

export function getAdminKey() {
  return _adminKey;
}

export function setAdminKey(key) {
  _adminKey = (key || "").trim();
}

// ─── Session Check (called on app init) ───

export async function checkSession() {
  if (_sessionChecked) return _isSessionAuthenticated;
  _sessionChecked = true;
  try {
    const res = await fetch(`${API}/api/session/me`, { credentials: "include" });
    if (res.ok) {
      const data = await res.json();
      if (data.authenticated) {
        _isSessionAuthenticated = true;
        _sessionRole = data.role || "";
        return true;
      }
    }
  } catch {
    // Network error — ignore, will fall through to key prompt
  }
  return false;
}

export function isSessionAuthenticated() {
  return _isSessionAuthenticated;
}

export function getSessionRole() {
  return _sessionRole;
}

// ─── Session Login (exchange API key for cookie) ───

export async function loginWithApiKey(apiKey) {
  try {
    const res = await fetch(`${API}/api/session`, {
      method: "POST",
      headers: { "X-API-Key": apiKey },
      credentials: "include",
    });
    if (res.ok) {
      const data = await res.json();
      _isSessionAuthenticated = true;
      _sessionRole = data.role || "";
      // The cookie is now set — clear the JS-memory key
      _apiKey = "";
      return true;
    }
  } catch {
    // Network error
  }
  return false;
}

// ─── Session Logout ───

export async function logoutSession() {
  try {
    await fetch(`${API}/api/session`, {
      method: "DELETE",
      credentials: "include",
    });
  } catch {
    // Ignore network errors during logout
  }
  _isSessionAuthenticated = false;
  _sessionRole = "";
}

// ─── Modal Key Management ───

let _pendingKeyType = null; // 'api' | 'admin'

function setupKeyModal(type) {
  const overlay = document.getElementById("apikey-overlay");
  const input = document.getElementById("apikey-input");
  const title = document.getElementById("apikey-modal-title");
  const desc = document.getElementById("apikey-modal-desc");
  const error = document.getElementById("apikey-error");

  if (!overlay || !input || !title || !desc || !error) return;

  error.classList.add("hidden");
  input.value = "";

  if (type === "admin") {
    title.textContent = "\u{1F6E1}\uFE0F Admin Key";
    desc.textContent =
      "Enter your DataForge Admin key for protected actions (session only — held in memory, not stored).";
  } else {
    title.textContent = "\u{1F511} API Key";
    desc.textContent = "Enter your DataForge API key. The key is held in memory only and is cleared on page reload.";
    // Pre-fill only with the in-memory copy; never read from storage.
    input.value = getApiKey() || "";
  }

  _pendingKeyType = type;
  overlay.classList.remove("hidden");
  attachFocusTrapTo(overlay);
  setTimeout(() => input.focus(), 100);
}

function closeKeyModal() {
  const overlay = document.getElementById("apikey-overlay");
  if (overlay) overlay.classList.add("hidden");
  _pendingKeyType = null;
  detachFocusTrapFrom();
}

function saveKeyFromModal() {
  if (!_pendingKeyType) return;

  const input = document.getElementById("apikey-input");
  const error = document.getElementById("apikey-error");
  if (!input || !error) return;

  const key = input.value.trim();

  if (!key) {
    error.textContent = "Please enter a key or click Cancel.";
    error.classList.remove("hidden");
    return;
  }

  if (_pendingKeyType === "admin") {
    setAdminKey(key);
    toast("Admin key set for this session", "success");
  } else {
    // G2: Exchange API key for session cookie
    setApiKey(key);
    toast("API key set", "success");
    loginWithApiKey(key)
      .then((ok) => {
        if (!ok) return;
        toast("Session cookie set", "success");
        refreshSystemStatus().catch((e) => console.warn("Failed to refresh status after auth:", e));
        refreshJobs().catch((e) => console.warn("Failed to refresh jobs after auth:", e));
      })
      .catch((e) => console.warn("Login flow error:", e));
  }

  closeKeyModal();
}

export function showApiKeyPrompt() {
  setupKeyModal("api");
}

export function showAdminKeyPrompt() {
  setupKeyModal("admin");
}

function isKeyModalVisible() {
  const overlay = document.getElementById("apikey-overlay");
  return overlay && !overlay.classList.contains("hidden");
}

// ─── 403 Throttle ───

let lastApi403 = 0;

// ─── Central Fetch Wrapper ───

export async function apiFetch(url, options = {}) {
  const { admin, ...rest } = options;
  // F-010: prefix relative ``/api/...`` URLs with ``API`` so requests
  // resolve to the backend (not the dev-server origin) when the frontend
  // is served from a different port (localhost:3000/5173). Several
  // modules (billing, audit, retention, workflows, aup, system-info,
  // recent-activity) pass relative URLs; in production (same-origin SPA)
  // the prefix is a no-op.
  const resolvedUrl = url.startsWith("/api/") ? `${API}${url}` : url;
  const headers = { ...(rest.headers || {}) };
  // For session-authenticated clients, the cookie is sent automatically.
  // Only attach X-API-Key for non-session (legacy) mode, or for admin ops
  // that need X-Admin-Key.
  if (admin) {
    const adminKey = getAdminKey();
    if (adminKey) {
      headers["X-Admin-Key"] = adminKey;
    }
  } else if (!_isSessionAuthenticated) {
    // Legacy mode: attach API key if we have one
    const key = getApiKey();
    if (key && (url.startsWith(API + "/api/") || url.startsWith("/api/"))) {
      headers["X-API-Key"] = key;
    }
  }
  const res = await fetch(resolvedUrl, { ...rest, headers, credentials: "include" });
  if (res.status === 403 && !admin) {
    const now = Date.now();
    if (now - lastApi403 > 15000 && !isKeyModalVisible()) {
      lastApi403 = now;
      showApiKeyPrompt();
    }
  }
  return res;
}

export { getApiKey, setApiKey, isKeyModalVisible, closeKeyModal, saveKeyFromModal, clearApiKey };
