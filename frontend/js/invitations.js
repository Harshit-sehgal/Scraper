/* ═══════════════════════════════════════════
   DataForge — Team Invitations View
   ═══════════════════════════════════════════ */

import { esc, toast } from "./utils.js";
import { apiFetch } from "./api.js";

export async function refreshInvitations() {
  await Promise.all([refreshPendingInvitations(), refreshOrgInvitations()]);
}

// ─── Pending Invitations ───────────────────────────────────────────

async function refreshPendingInvitations() {
  const list = document.getElementById("invitations-pending-list");
  if (!list) return;

  list.innerHTML = '<span class="spinner"></span> Loading…';

  try {
    const res = await apiFetch("/api/saas/invitations/pending");
    if (!res.ok) {
      if (res.status === 401) {
        list.innerHTML = '<p class="subtle">Please sign in to see your invitations.</p>';
        return;
      }
      throw new Error("Failed to load");
    }
    const data = await res.json();
    const items = Array.isArray(data) ? data : [];

    if (!items.length) {
      list.innerHTML = '<p class="subtle">No pending invitations.</p>';
      return;
    }

    list.innerHTML = items
      .map(
        (inv) => `
        <div class="invitation-item">
          <div class="invitation-info">
            <strong>Invited to:</strong> ${esc(inv.org_id)}
            <span class="badge pending">${esc(inv.role)}</span>
            <span class="hint">Expires: ${esc(new Date(inv.expires_at).toLocaleDateString())}</span>
          </div>
          <div class="invitation-actions">
            <button type="button" class="btn primary small" data-action="accept-invitation" data-id="${esc(inv.id)}">
              Accept
            </button>
            <button type="button" class="btn ghost small" data-action="decline-invitation" data-id="${esc(inv.id)}">
              Decline
            </button>
          </div>
        </div>
      `,
      )
      .join("");
  } catch (err) {
    list.innerHTML = `<p class="subtle">Error: ${esc(err.message)}</p>`;
  }
}

export async function respondToInvitation(invitationId, accept) {
  const action = accept ? "accept" : "decline";
  try {
    const res = await apiFetch(`/api/saas/invitations/${encodeURIComponent(invitationId)}/respond`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ accept }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `Failed to ${action} invitation`);

    toast(`Invitation ${data.status}!`, "success");
    await refreshInvitations();
  } catch (err) {
    toast(`Error: ${err.message}`, "error");
  }
}

// ─── Org Invitations (Create + List) ───────────────────────────────

async function loadOrgSelects() {
  const createSelect = document.getElementById("invite-org-select");
  const filterSelect = document.getElementById("invitations-org-filter");
  if (!createSelect) return;

  try {
    const res = await apiFetch("/api/saas/orgs");
    if (!res.ok) return;
    const data = await res.json();
    const orgs = Array.isArray(data.items) ? data.items : [];

    const options = orgs.map((o) => `<option value="${esc(o.id)}">${esc(o.name)}</option>`);

    if (createSelect) {
      createSelect.innerHTML = `<option value="">Select an org…</option>${options.join("")}`;
    }
    if (filterSelect) {
      filterSelect.innerHTML = `<option value="">All</option>${options.join("")}`;
    }
  } catch {
    // Org loading failed — leave selects as-is
  }
}

async function refreshOrgInvitations() {
  const list = document.getElementById("invitations-org-list");
  const statusFilter = document.getElementById("invitations-status-filter");
  const orgFilter = document.getElementById("invitations-org-filter");
  if (!list) return;

  list.innerHTML = '<span class="spinner"></span> Loading…';
  await loadOrgSelects();

  const status = statusFilter ? statusFilter.value : "";
  const orgId = orgFilter ? orgFilter.value : "";

  try {
    // First get user's orgs
    const orgsRes = await apiFetch("/api/saas/orgs");
    if (!orgsRes.ok) {
      list.innerHTML = '<p class="subtle">Please sign in to manage invitations.</p>';
      return;
    }
    const orgsData = await orgsRes.json();
    const orgs = Array.isArray(orgsData.items) ? orgsData.items : [];

    let allInvitations = [];

    for (const org of orgs) {
      if (orgId && org.id !== orgId) continue;
      try {
        const query = status ? `?status=${encodeURIComponent(status)}` : "";
        const invRes = await apiFetch(`/api/saas/orgs/${encodeURIComponent(org.id)}/invitations${query}`);
        if (invRes.ok) {
          const invData = await invRes.json();
          const items = Array.isArray(invData.items) ? invData.items : [];
          allInvitations = allInvitations.concat(items.map((inv) => ({ ...inv, org_name: org.name })));
        }
      } catch {
        // Skip orgs that fail to load
      }
    }

    if (!allInvitations.length) {
      list.innerHTML = '<p class="subtle">No invitations found.</p>';
      return;
    }

    list.innerHTML = allInvitations
      .map(
        (inv) => `
        <div class="invitation-item">
          <div class="invitation-info">
            <strong>${esc(inv.org_name)}</strong>
            <span>→ ${esc(inv.invited_email)}</span>
            <span class="badge ${esc(inv.status)}">${esc(inv.status)}</span>
            <span class="hint">Role: ${esc(inv.role)}</span>
          </div>
          <div class="invitation-meta">
            <span class="hint">Created: ${esc(new Date(inv.created_at).toLocaleDateString())}</span>
            ${inv.responded_at ? `<span class="hint">Responded: ${esc(new Date(inv.responded_at).toLocaleDateString())}</span>` : ""}
          </div>
        </div>
      `,
      )
      .join("");
  } catch (err) {
    list.innerHTML = `<p class="subtle">Error: ${esc(err.message)}</p>`;
  }
}

export async function createInvitation() {
  const orgSelect = document.getElementById("invite-org-select");
  const emailInput = document.getElementById("invite-email-input");
  const roleSelect = document.getElementById("invite-role-select");
  const resultEl = document.getElementById("invite-create-result");

  const orgId = orgSelect ? orgSelect.value : "";
  const email = emailInput ? emailInput.value.trim() : "";
  const role = roleSelect ? roleSelect.value : "member";

  if (!orgId) {
    toast("Select an organization", "error");
    return;
  }
  if (!email) {
    toast("Enter an email address", "error");
    return;
  }

  try {
    const res = await apiFetch(`/api/saas/orgs/${encodeURIComponent(orgId)}/invitations`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, role }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Failed to create invitation");

    if (resultEl) {
      resultEl.textContent = `Invitation sent to ${data.invited_email}!`;
      resultEl.className = "invite-result success";
      resultEl.classList.remove("hidden");
    }
    toast("Invitation sent!", "success");

    // Clear the form
    if (emailInput) emailInput.value = "";
    await refreshOrgInvitations();
  } catch (err) {
    if (resultEl) {
      resultEl.textContent = err.message;
      resultEl.className = "invite-result error";
      resultEl.classList.remove("hidden");
    }
    toast(`Error: ${err.message}`, "error");
  }
}

// ─── Filter change handler ─────────────────────────────────────────

export function onInvitationsFilterChanged() {
  refreshOrgInvitations();
}
