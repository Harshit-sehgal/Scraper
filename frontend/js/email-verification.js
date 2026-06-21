/* ═══════════════════════════════════════════
   DataForge — Email Verification View
   ═══════════════════════════════════════════ */

import { esc, toast } from "./utils.js";
import { apiFetch } from "./api.js";

export async function refreshEmailVerification() {
  const statusEl = document.getElementById("email-verify-status");
  const actionsEl = document.getElementById("email-verify-actions");
  const resultEl = document.getElementById("email-verify-result");

  if (statusEl) statusEl.innerHTML = '<span class="spinner"></span> Loading…';

  try {
    const res = await apiFetch("/api/saas/email-verification/status");
    if (!res.ok) {
      if (res.status === 401) {
        statusEl.innerHTML = '<p class="subtle">Please sign in to check your email verification status.</p>';
        return;
      }
      throw new Error("Failed to load status");
    }
    const data = await res.json();

    const verified = data.email_verified;
    statusEl.innerHTML = `
      <div class="email-verify-status-row">
        <span class="email-verify-label">Email:</span>
        <span class="email-verify-value">${esc(data.email)}</span>
      </div>
      <div class="email-verify-status-row">
        <span class="email-verify-label">Verified:</span>
        <span class="email-verify-value">
          <span class="badge ${verified ? "completed" : "failed"}">${verified ? "Yes" : "No"}</span>
        </span>
      </div>
      ${
        data.email_verified_at
          ? `
        <div class="email-verify-status-row">
          <span class="email-verify-label">Verified at:</span>
          <span class="email-verify-value">${esc(new Date(data.email_verified_at).toLocaleString())}</span>
        </div>
      `
          : ""
      }
    `;

    // Show/hide action buttons based on status
    if (actionsEl) {
      const sendBtn = actionsEl.querySelector("#btn-send-verification");
      if (sendBtn) sendBtn.style.display = verified ? "none" : "";
    }

    if (resultEl) {
      resultEl.classList.add("hidden");
      resultEl.textContent = "";
    }
  } catch (err) {
    if (statusEl) statusEl.innerHTML = `<p class="subtle">Error: ${esc(err.message)}</p>`;
  }
}

export async function sendEmailVerification() {
  const btn = document.getElementById("btn-send-verification");
  const resultEl = document.getElementById("email-verify-result");
  const prevText = btn ? btn.textContent : "";

  if (btn) {
    btn.disabled = true;
    btn.textContent = "Sending…";
  }

  try {
    const res = await apiFetch("/api/saas/email-verification/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Failed to send verification");

    if (resultEl) {
      resultEl.textContent = data.message || "Verification email sent! Check the server logs for the token.";
      resultEl.className = "email-verify-result success";
      resultEl.classList.remove("hidden");
    }
    toast("Verification email sent", "success");
  } catch (err) {
    if (resultEl) {
      resultEl.textContent = err.message;
      resultEl.className = "email-verify-result error";
      resultEl.classList.remove("hidden");
    }
    toast(`Error: ${err.message}`, "error");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = prevText || "Send Verification Email";
    }
  }
}

export async function verifyEmailToken() {
  const input = document.getElementById("email-verify-token-input");
  const btn = document.getElementById("btn-verify-token");
  const resultEl = document.getElementById("email-verify-result");
  const token = input ? input.value.trim() : "";

  if (!token) {
    toast("Enter a verification token", "error");
    return;
  }

  if (btn) {
    btn.disabled = true;
    btn.textContent = "Verifying…";
  }

  try {
    const res = await apiFetch("/api/saas/email-verification/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Verification failed");

    if (resultEl) {
      resultEl.textContent = "Email verified successfully!";
      resultEl.className = "email-verify-result success";
      resultEl.classList.remove("hidden");
    }
    toast("Email verified!", "success");

    // Refresh the status display
    await refreshEmailVerification();
    if (input) input.value = "";
  } catch (err) {
    if (resultEl) {
      resultEl.textContent = err.message;
      resultEl.className = "email-verify-result error";
      resultEl.classList.remove("hidden");
    }
    toast(`Error: ${err.message}`, "error");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "Verify";
    }
  }
}
