/* ═══════════════════════════════════════════
   DataForge — API Keys Page
   ═══════════════════════════════════════════ */

import {
  getApiKey,
  setApiKey,
  clearApiKey,
  getAdminKey,
  setAdminKey,
  isSessionAuthenticated,
  getSessionRole,
  getSessionUser,
  loginWithApiKey,
  logoutSession,
  checkSession,
  isAdminOrOperator,
  API,
} from "./api.js";
import { refreshSystemStatus, refreshJobs } from "./jobs.js";
import { esc, toast } from "./utils.js";

// ─── Masking helpers ───

function _maskKey(key) {
  if (!key) return "";
  if (key.length <= 8) return "••••••••";
  const prefix = key.slice(0, 8);
  const suffix = key.slice(-4);
  return `${prefix}${"•".repeat(Math.min(key.length - 12, 20))}${suffix}`;
}

function _prefixKey(key) {
  if (!key) return "—";
  return key.slice(0, 12) + "…";
}

// ─── Page refresh ───

export async function refreshApiKeysPage() {
  const apiKey = getApiKey();
  const adminKey = getAdminKey();

  // ── API Key card ──
  const apiKeyStatus = document.getElementById("api-key-status");
  const apiKeyInput = document.getElementById("api-key-input");
  const apiKeyDisplay = document.getElementById("api-key-display");
  const apiKeyCreated = document.getElementById("api-key-created");
  const apiKeyLastUsed = document.getElementById("api-key-last-used");

  if (apiKeyStatus) {
    apiKeyStatus.textContent = apiKey ? "Active" : "Not set";
    apiKeyStatus.className = "badge" + (apiKey ? " completed" : "");
  }
  if (apiKeyInput) {
    apiKeyInput.value = apiKey || "";
  }
  if (apiKeyDisplay) {
    apiKeyDisplay.textContent = apiKey ? _maskKey(apiKey) : "pk_live_••••••••••••";
    apiKeyDisplay.dataset.visible = "false";
  }
  if (apiKeyCreated) {
    apiKeyCreated.textContent = "Created: " + (apiKey ? "this session" : "—");
  }
  if (apiKeyLastUsed) {
    apiKeyLastUsed.textContent = "Last used: " + (apiKey ? "just now" : "—");
  }

  // ── Admin Key card ──
  const adminKeyStatus = document.getElementById("admin-key-status");
  const adminKeyInput = document.getElementById("admin-key-input");
  const adminKeyDisplay = document.getElementById("admin-key-display");
  const adminKeyCreated = document.getElementById("admin-key-created");
  const adminKeyRevoked = document.getElementById("admin-key-revoked");

  if (adminKeyStatus) {
    adminKeyStatus.textContent = adminKey ? "Set" : "Inactive";
    adminKeyStatus.className = "badge" + (adminKey ? " running" : " canceled");
  }
  if (adminKeyInput) {
    adminKeyInput.value = adminKey || "";
  }
  if (adminKeyDisplay) {
    adminKeyDisplay.textContent = adminKey ? _maskKey(adminKey) : "sk_admin_••••••••••••••";
    adminKeyDisplay.dataset.visible = "false";
  }
  if (adminKeyCreated) {
    adminKeyCreated.textContent = "Created: " + (adminKey ? "this session" : "—");
  }
  if (adminKeyRevoked) {
    adminKeyRevoked.textContent = "Revoked: —";
  }

  // ── Session card ──
  const sessionStatus = document.getElementById("session-status");
  const sessionInfo = document.getElementById("session-info");
  const authed = isSessionAuthenticated();
  const role = getSessionRole();
  const user = getSessionUser();

  if (sessionStatus) {
    sessionStatus.textContent = authed ? "Active" : "Inactive";
    sessionStatus.className = "badge" + (authed ? " running" : "");
  }

  if (sessionInfo) {
    if (authed && user) {
      sessionInfo.innerHTML = `
        <div class="api-keys-session-row">
          <span class="api-keys-session-label">User ID</span>
          <span class="api-keys-session-value">${esc(user.user_id || "") || "—"}</span>
        </div>
        <div class="api-keys-session-row">
          <span class="api-keys-session-label">Role</span>
          <span class="api-keys-session-value">${esc(role) || "—"}</span>
        </div>
        <div class="api-keys-session-row">
          <span class="api-keys-session-label">Admin access</span>
          <span class="api-keys-session-value">${isAdminOrOperator() ? "Yes" : "No"}</span>
        </div>`;
    } else {
      sessionInfo.innerHTML = '<p class="subtle">No active session. Set an API key to authenticate.</p>';
    }
  }

  // Update the settings page API URL too
  const settingsApiUrl = document.getElementById("settings-api-url");
  if (settingsApiUrl) {
    settingsApiUrl.textContent = API;
  }

  // ── Access log table (placeholder — no backend endpoint yet) ──
  _renderAccessLogPlaceholder();
}

// ─── Access log rendering ───

function _renderAccessLogPlaceholder() {
  const tbody = document.getElementById("access-log-list");
  if (!tbody) return;
  // If we already have real rows, don't overwrite
  if (tbody.querySelector("tr:not(.empty-row)")) return;
  tbody.innerHTML = `
    <tr class="empty-row">
      <td colspan="5">
        <div class="empty-state">
          <p class="subtle">No access logs available yet.</p>
        </div>
      </td>
    </tr>`;
}

// ─── Action Handlers ───

export function saveApiKeyFromPage() {
  const input = document.getElementById("api-key-input");
  if (!input) return;
  const key = input.value.trim();
  if (!key) {
    toast("Enter an API key first", "warning");
    return;
  }
  setApiKey(key);
  // Hide the key input after saving
  input.type = "password";
  loginWithApiKey(key)
    .then((ok) => {
      if (ok) {
        toast("API key saved and session established", "success");
        refreshSystemStatus().catch((e) => console.warn("Op:", e));
        refreshJobs().catch((e) => console.warn("Op:", e));
      } else {
        toast("Key saved but session could not be established", "warning");
      }
      refreshApiKeysPage();
    })
    .catch(() => {
      toast("Key saved (session check failed)", "warning");
      refreshApiKeysPage();
    });
}

export function clearApiKeyFromPage() {
  clearApiKey();
  toast("API key cleared", "info");
  refreshApiKeysPage();
}

export function saveAdminKeyFromPage() {
  const input = document.getElementById("admin-key-input");
  if (!input) return;
  const key = input.value.trim();
  if (!key) {
    toast("Enter an admin key first", "warning");
    return;
  }
  setAdminKey(key);
  input.type = "password";
  toast("Admin key saved for this session", "success");
  refreshApiKeysPage();
}

export function clearAdminKeyFromPage() {
  setAdminKey("");
  toast("Admin key cleared", "info");
  refreshApiKeysPage();
}

export function toggleApiKeyVisibility() {
  const input = document.getElementById("api-key-input");
  const display = document.getElementById("api-key-display");
  const btn = document.getElementById("btn-api-key-toggle-vis");

  const key = getApiKey();
  if (!key) {
    // No key set — toggle input field type
    if (input) input.type = input.type === "password" ? "text" : "password";
    return;
  }

  // Key is set — toggle the display row
  if (display) {
    const isVisible = display.dataset.visible === "true";
    if (isVisible) {
      display.textContent = _maskKey(key);
      display.dataset.visible = "false";
      if (btn) btn.title = "Show Key";
    } else {
      display.textContent = key;
      display.dataset.visible = "true";
      if (btn) btn.title = "Hide Key";
    }
  }
  if (input) input.type = "password";
}

export function toggleAdminKeyVisibility() {
  const input = document.getElementById("admin-key-input");
  const display = document.getElementById("admin-key-display");
  const btn = document.getElementById("btn-admin-key-toggle-vis");

  const key = getAdminKey();
  if (!key) {
    if (input) input.type = input.type === "password" ? "text" : "password";
    return;
  }

  if (display) {
    const isVisible = display.dataset.visible === "true";
    if (isVisible) {
      display.textContent = _maskKey(key);
      display.dataset.visible = "false";
      if (btn) btn.title = "Show Key";
    } else {
      display.textContent = key;
      display.dataset.visible = "true";
      if (btn) btn.title = "Hide Key";
    }
  }
  if (input) input.type = "password";
}

export function copyApiKey() {
  const key = getApiKey();
  if (!key) {
    toast("No API key to copy", "warning");
    return;
  }
  navigator.clipboard
    .writeText(key)
    .then(() => toast("API key copied to clipboard", "success"))
    .catch(() => toast("Failed to copy key", "error"));
}

export async function logoutFromPage() {
  await logoutSession();
  toast("Signed out", "info");
  refreshApiKeysPage();
}

export async function refreshSession() {
  await checkSession();
  refreshApiKeysPage();
}

export function generateApiKey() {
  toast("Key generation requires backend support — use an existing key for now", "info");
}
