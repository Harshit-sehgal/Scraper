/* ═══════════════════════════════════════════
   DataForge — Auth Profiles Management
   ═══════════════════════════════════════════ */

import { API, apiFetch } from "./api.js";
import { attrStr, esc, showConfirm, toast } from "./utils.js";

// ─── State ───
let _allProfiles = [];
let _isLoading = false;

// ─── Helpers ───
function _formatDate(value) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString([], { year: "numeric", month: "2-digit", day: "2-digit" });
}

function _formatTimestamp(value) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  return (
    d.toLocaleString([], {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    }) + " UTC"
  );
}

function _authProfileRow(profile) {
  const isExpired = profile.status === "expired" || profile.status === "revoked" || profile.status === "failed";
  const rowClass = isExpired ? "profile-expired" : "";
  const expiryClass = isExpired ? "expired" : "";

  const statusBadgeClass =
    {
      active: "badge completed",
      pending_login: "badge discovering",
      expired: "badge failed",
      revoked: "badge canceled",
      failed: "badge failed",
    }[profile.status] || "badge pending";

  const statusLabel = profile.status.replace(/_/g, " ");

  // Build actions based on status — matching auth_profiles_app_auth_profiles stitch
  let actions = "";
  if (profile.status === "active" || profile.status === "pending_login") {
    actions += `<a class="action-link" data-action="reconnect-auth-profile" data-id="${attrStr(profile.id)}">Edit</a> `;
    actions += `<a class="action-link action-muted" data-action="validate-auth-profile" data-id="${attrStr(profile.id)}">Test</a> `;
    actions += `<a class="action-link action-remove" data-action="revoke-auth-profile" data-id="${attrStr(profile.id)}">Remove</a>`;
  } else if (profile.status === "expired") {
    actions += `<a class="action-link" data-action="reconnect-auth-profile" data-id="${attrStr(profile.id)}">Renew</a> `;
    actions += `<a class="action-link action-remove" data-action="revoke-auth-profile" data-id="${attrStr(profile.id)}">Remove</a>`;
  } else {
    actions += `<a class="action-link" data-action="reconnect-auth-profile" data-id="${attrStr(profile.id)}">Reconnect</a> `;
    actions += `<a class="action-link action-remove" data-action="revoke-auth-profile" data-id="${attrStr(profile.id)}">Remove</a>`;
  }

  return `
    <tr class="${rowClass}" data-profile-id="${attrStr(profile.id)}">
      <td class="col-profile-name" data-label="Profile Name">${esc(profile.name)}</td>
      <td class="col-profile-domain" data-label="Target Domain">${esc(profile.domain)}</td>
      <td class="col-profile-last-used" data-label="Last Used">${esc(_formatTimestamp(profile.last_used || profile.updated_at))}</td>
      <td class="col-profile-expiry ${expiryClass}" data-label="Expiry">${esc(_formatDate(profile.expires_at))}</td>
      <td class="col-profile-status" data-label="Status"><span class="${statusBadgeClass}">${esc(statusLabel)}</span></td>
      <td class="col-profile-actions" data-label="Actions">${actions}</td>
    </tr>
  `;
}

function _renderProfiles(profiles) {
  const tbody = document.getElementById("auth-profiles-list");
  const emptyRow = document.getElementById("auth-profiles-empty-state-row");
  const rangeEl = document.getElementById("auth-profiles-pagination-range");

  if (!tbody) return;

  if (profiles.length === 0) {
    tbody.innerHTML = "";
    if (emptyRow) {
      tbody.appendChild(emptyRow);
      const empty = emptyRow.querySelector("#auth-profiles-empty-state");
      if (empty) empty.style.display = "";
    }
    if (rangeEl) rangeEl.textContent = "Showing 0 profiles";
    return;
  }

  // Hide empty state
  tbody.innerHTML = profiles.map((p) => _authProfileRow(p)).join("");

  // Pagination range
  if (rangeEl) {
    rangeEl.textContent = `Showing 1 to ${profiles.length} of ${_allProfiles.length} profiles`;
  }

  // Re-attach event listeners
  tbody.querySelectorAll("[data-action='reconnect-auth-profile']").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      const id = e.currentTarget.dataset.id;
      reconnectAuthProfile(id);
    });
  });

  tbody.querySelectorAll("[data-action='revoke-auth-profile']").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      const id = e.currentTarget.dataset.id;
      revokeAuthProfile(id);
    });
  });

  tbody.querySelectorAll("[data-action='validate-auth-profile']").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      const id = e.currentTarget.dataset.id;
      validateAuthProfile(id);
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
    const res = await apiFetch(`${API}/api/auth-profiles`);
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

    const res = await apiFetch(`${API}/api/auth-profiles?${params.toString()}`, {
      method: "POST",
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
    const res = await apiFetch(`${API}/api/auth-profiles/${profileId}/start-login`, {
      method: "POST",
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
  showConfirm(
    "Revoke Auth Profile?",
    `Revoke auth profile "${profile?.name || profileId}"? This will invalidate the stored session.`,
    async () => {
      try {
        const res = await apiFetch(`${API}/api/auth-profiles/${profileId}/revoke`, {
          method: "POST",
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
    },
  );
}

export async function validateAuthProfile(profileId) {
  try {
    const res = await apiFetch(`${API}/api/auth-profiles/${profileId}/validate`, {
      method: "POST",
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
