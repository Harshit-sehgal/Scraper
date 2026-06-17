/* ═══════════════════════════════════
   DataForge — AUP banner / acceptance
   ═══════════════════════════════════ */

import { apiFetch } from "./api.js";
import { toast } from "./utils.js";

const STORAGE_KEY = "dataforge_aup_accepted_version";

let _checked = false;
let _accepted = false;
let _acceptedVersion = "";

function safeReadAcceptedVersion() {
  try {
    return localStorage.getItem(STORAGE_KEY) || "";
  } catch {
    return "";
  }
}

function safeWriteAcceptedVersion(v) {
  try {
    if (v) localStorage.setItem(STORAGE_KEY, v);
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* localStorage may be blocked */
  }
}

/**
 * Check the user's current AUP status and render (or remove) the
 * banner. Safe to call repeatedly — it short-circuits if the last
 * check was successful.
 */
export async function checkAndRenderAupBanner(currentAupVersion) {
  if (!currentAupVersion) return;
  const banner = document.getElementById("aup-banner");
  if (!banner) return;

  if (_checked && _accepted && _acceptedVersion === currentAupVersion) {
    // Already known-good, do nothing.
    return;
  }

  try {
    const resp = await apiFetch("/api/saas/aup/status");
    if (resp.status === 404 || resp.status === 401) {
      banner.remove();
      return;
    }
    if (!resp.ok) {
      // Transient error: don't nag the user, but leave any prior banner alone.
      return;
    }
    const data = await resp.json();
    const acceptedVersion = data.aup_version_accepted || safeReadAcceptedVersion();
    _accepted = Boolean(data.aup_accepted_at) || Boolean(acceptedVersion);
    _acceptedVersion = acceptedVersion;
    _checked = true;

    if (_accepted && _acceptedVersion === currentAupVersion) {
      banner.remove();
    } else {
      renderBanner(banner, currentAupVersion, _accepted, _acceptedVersion);
    }
  } catch {
    // Network error: stay quiet, the user can retry by reloading.
  }
}

function renderBanner(banner, currentVersion, accepted, acceptedVersion) {
  banner.classList.toggle("aup-banner-pending", !accepted);
  banner.classList.toggle("aup-banner-stale", accepted && acceptedVersion !== currentVersion);
  banner.innerHTML = "";

  const text = document.createElement("div");
  text.className = "aup-banner-text";
  if (!accepted) {
    text.textContent = "You must accept the Acceptable Use Policy before running jobs against external sites.";
  } else {
    text.textContent = `AUP v${acceptedVersion} accepted. New version v${currentVersion} requires re-acceptance.`;
  }
  banner.appendChild(text);

  const actions = document.createElement("div");
  actions.className = "aup-banner-actions";
  const accept = document.createElement("button");
  accept.type = "button";
  accept.className = "btn primary small";
  accept.textContent = accepted ? "Re-accept AUP" : "Accept AUP";
  accept.setAttribute("data-action", "aup-accept");
  accept.setAttribute("data-version", currentVersion);
  actions.appendChild(accept);

  const dismiss = document.createElement("button");
  dismiss.type = "button";
  dismiss.className = "btn ghost small";
  dismiss.textContent = "Dismiss";
  dismiss.setAttribute("data-action", "aup-dismiss");
  actions.appendChild(dismiss);

  banner.appendChild(actions);
  banner.style.display = "flex";
}

export async function acceptAup(version) {
  if (!version) return;
  try {
    const resp = await apiFetch("/api/saas/aup/accept", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ aup_version: version }),
    });
    if (!resp.ok) {
      toast(`AUP acceptance failed: HTTP ${resp.status}`, "error");
      return;
    }
    _accepted = true;
    _acceptedVersion = version;
    safeWriteAcceptedVersion(version);
    const banner = document.getElementById("aup-banner");
    if (banner) banner.remove();
    toast("AUP accepted.", "ok");
  } catch (err) {
    toast(`AUP acceptance failed: ${err.message || err}`, "error");
  }
}

export function dismissAupBanner() {
  const banner = document.getElementById("aup-banner");
  if (banner) banner.remove();
}
