/* ═══════════════════════════════════════════
   DataForge — Auth Profiles Management
   ═══════════════════════════════════════════ */

import { API } from "./api.js";
import { toast } from "./utils.js";

// ─── State ───
let _allProfiles = [];
let _isLoading = false;

// ─── Helpers ───
function _authProfileRow(profile) {
  const statusBadgeClass =
    {
      active: "badge completed",
      pending_login: "badge discovering",
      expired: "badge failed",
      revoked: "badge canceled",
      failed: "badge failed",
    }[profile.status] || "badge pending";

  const statusLabel = profile.status.replace(/_/g, " ");

  return `
    <div class="job-row" data-profile-id="${profile.id}">
      <div class="job-name-col">
        <div class="job-name">${profile.name}</div>
        <div class="job-urls">${profile.description || ""}</div>
      </div>
      <div class="job-urls">${profile.domain}</div>
      <div>
        <span class="${statusBadgeClass}">${statusLabel}</span>
      </div>
      <div class="job-actions">
        ${profile.status === "active" || profile.status === "expired" ? `<button type="button" class="btn ghost small" data-action="reconnect-auth-profile" data-id="${profile.id}">🔗 Reconnect</button>` : ""}
        <button type="button" class="btn danger-ghost small" data-action="revoke-auth-profile" data-id="${profile.id}">Revoke</button>
      </div>
    </div>
  `;
}

function _renderProfiles(profiles) {
  const container = document.getElementById("auth-profiles-list");
  const emptyState = document.getElementById("auth-profiles-empty-state");

  if (!container) return;

  // Remove existing rows (keep empty state)
  Array.from(container.querySelectorAll(".job-row")).forEach((row) => row.remove());

  if (profiles.length === 0) {
    if (emptyState) emptyState.style.display = "";
    return;
  }

  if (emptyState) emptyState.style.display = "none";

  for (const profile of profiles) {
    const wrapper = document.createElement("div");
    wrapper.innerHTML = _authProfileRow(profile);
    container.appendChild(wrapper.firstElementChild);
  }

  // Re-attach event listeners
  container.querySelectorAll("[data-action='reconnect-auth-profile']").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      const id = e.currentTarget.dataset.id;
      reconnectAuthProfile(id);
    });
  });

  container.querySelectorAll("[data-action='revoke-auth-profile']").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      const id = e.currentTarget.dataset.id;
      revokeAuthProfile(id);
    });
  });
}

function _updateKPIs(profiles) {
  const total = profiles.length;
  const active = profiles.filter((p) => p.status === "active").length;
  const pending = profiles.filter((p) => p.status === "pending_login").length;
  const expired = profiles.filter(
    (p) => p.status === "expired" || p.status === "revoked" || p.status === "failed",
  ).length;

  const totalEl = document.getElementById("kpi-total-auth-profiles");
  const activeEl = document.getElementById("kpi-active-auth-profiles");
  const pendingEl = document.getElementById("kpi-pending-auth-profiles");
  const expiredEl = document.getElementById("kpi-expired-auth-profiles");

  if (totalEl) totalEl.textContent = total;
  if (activeEl) activeEl.textContent = active;
  if (pendingEl) pendingEl.textContent = pending;
  if (expiredEl) expiredEl.textContent = expired;

  const updatedEl = document.getElementById("auth-profiles-last-updated");
  if (updatedEl) {
    updatedEl.textContent = "Updated " + new Date().toLocaleTimeString();
  }
}

// ─── API Operations ───

export async function refreshAuthProfiles() {
  if (_isLoading) return;
  _isLoading = true;

  try {
    const res = await fetch(`${API}/api/auth-profiles`, { credentials: "include" });
    if (!res.ok) {
      if (res.status === 401 || res.status === 403) {
        toast("Authentication required to view auth profiles.", "warning");
        return;
      }
      throw new Error("Failed to fetch auth profiles");
    }
    const data = await res.json();
    _allProfiles = data.items || [];
    _renderProfiles(_allProfiles);
    _updateKPIs(_allProfiles);
  } catch (err) {
    toast(err.message || "Failed to load auth profiles", "error");
  } finally {
    _isLoading = false;
  }
}

export async function createAuthProfile(name, domain, description = "") {
  try {
    const params = new URLSearchParams({ name, domain });
    if (description) params.append("description", description);

    const res = await fetch(`${API}/api/auth-profiles?${params.toString()}`, {
      method: "POST",
      credentials: "include",
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to create auth profile");
    }
    toast("Auth profile created successfully", "success");
    await refreshAuthProfiles();
    return await res.json();
  } catch (err) {
    toast(err.message, "error");
    throw err;
  }
}

export async function reconnectAuthProfile(profileId) {
  try {
    const res = await fetch(`${API}/api/auth-profiles/${profileId}/start-login`, {
      method: "POST",
      credentials: "include",
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to start login flow");
    }
    const data = await res.json();
    toast(data.message || "Login flow started. Complete in a new browser window.", "info");
    // In a real implementation, this would open a popup or redirect
    return data;
  } catch (err) {
    toast(err.message, "error");
    throw err;
  }
}

export async function revokeAuthProfile(profileId) {
  const profile = _allProfiles.find((p) => p.id === profileId);
  const confirm = window.confirm(
    `Revoke auth profile "${profile?.name || profileId}"? This will invalidate the stored session.`,
  );
  if (!confirm) return;

  try {
    const res = await fetch(`${API}/api/auth-profiles/${profileId}/revoke`, {
      method: "POST",
      credentials: "include",
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to revoke auth profile");
    }
    toast("Auth profile revoked successfully", "success");
    await refreshAuthProfiles();
  } catch (err) {
    toast(err.message, "error");
    throw err;
  }
}

export async function validateAuthProfile(profileId) {
  try {
    const res = await fetch(`${API}/api/auth-profiles/${profileId}/validate`, {
      method: "POST",
      credentials: "include",
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to validate auth profile");
    }
    const data = await res.json();
    const statusMsg = data.valid ? "valid" : `invalid (${data.reason})`;
    toast(`Profile validation: ${statusMsg}`, data.valid ? "success" : "warning");
    await refreshAuthProfiles();
    return data;
  } catch (err) {
    toast(err.message, "error");
    throw err;
  }
}

// ─── Search ───

function _onSearch() {
  const query = document.getElementById("auth-profiles-search")?.value.toLowerCase() || "";
  if (!query) {
    _renderProfiles(_allProfiles);
    return;
  }
  const filtered = _allProfiles.filter(
    (p) =>
      p.name.toLowerCase().includes(query) ||
      p.domain.toLowerCase().includes(query) ||
      (p.description || "").toLowerCase().includes(query),
  );
  _renderProfiles(filtered);
}

// ─── Initialization ───

export function initAuthProfiles() {
  const searchInput = document.getElementById("auth-profiles-search");
  if (searchInput) {
    searchInput.addEventListener("input", _onSearch);
  }

  const refreshBtn = document.getElementById("btn-refresh-auth-profiles");
  if (refreshBtn) {
    refreshBtn.addEventListener("click", refreshAuthProfiles);
  }
}
