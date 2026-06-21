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
import { toast } from "./utils.js";

export async function refreshApiKeysPage() {
  // API Key status
  const apiKeyStatus = document.getElementById("api-key-status");
  const apiKeyInput = document.getElementById("api-key-input");
  if (apiKeyStatus) {
    const hasKey = !!getApiKey();
    apiKeyStatus.textContent = hasKey ? "Set" : "Not set";
    apiKeyStatus.className = "badge" + (hasKey ? " running" : "");
  }
  if (apiKeyInput) {
    apiKeyInput.value = getApiKey() || "";
  }

  // Admin Key status
  const adminKeyStatus = document.getElementById("admin-key-status");
  const adminKeyInput = document.getElementById("admin-key-input");
  if (adminKeyStatus) {
    const hasKey = !!getAdminKey();
    adminKeyStatus.textContent = hasKey ? "Set" : "Not set";
    adminKeyStatus.className = "badge" + (hasKey ? " running" : "");
  }
  if (adminKeyInput) {
    adminKeyInput.value = getAdminKey() || "";
  }

  // Session status
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
          <span class="api-keys-session-value">${user.user_id || "—"}</span>
        </div>
        <div class="api-keys-session-row">
          <span class="api-keys-session-label">Role</span>
          <span class="api-keys-session-value">${role || "—"}</span>
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
  loginWithApiKey(key)
    .then((ok) => {
      if (ok) {
        toast("API key saved and session established", "success");
        refreshSystemStatus().catch(() => {});
        refreshJobs().catch(() => {});
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
  if (input) {
    input.type = input.type === "password" ? "text" : "password";
  }
}

export function toggleAdminKeyVisibility() {
  const input = document.getElementById("admin-key-input");
  if (input) {
    input.type = input.type === "password" ? "text" : "password";
  }
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
