/* ═══════════════════════════════════════════
   DataForge — Password Reset View
   ═══════════════════════════════════════════ */

import { toast } from "./utils.js";
import { apiFetch } from "./api.js";

export async function requestPasswordReset() {
  const input = document.getElementById("pwd-reset-email-input");
  const btn = document.getElementById("btn-request-reset");
  const resultEl = document.getElementById("pwd-reset-request-result");
  const email = input ? input.value.trim() : "";

  if (!email) {
    toast("Enter your email address", "error");
    return;
  }

  if (btn) {
    btn.disabled = true;
    btn.textContent = "Sending…";
  }

  try {
    const res = await apiFetch("/api/saas/password-reset/request", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Request failed");

    if (resultEl) {
      resultEl.textContent = data.message || "If that email exists, a reset link has been sent.";
      resultEl.className = "pwd-reset-result success";
      resultEl.classList.remove("hidden");
    }
    toast("Reset request sent", "success");
  } catch (err) {
    if (resultEl) {
      resultEl.textContent = err.message;
      resultEl.className = "pwd-reset-result error";
      resultEl.classList.remove("hidden");
    }
    toast(`Error: ${err.message}`, "error");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "Send Reset Token";
    }
  }
}

export async function confirmPasswordReset() {
  const tokenInput = document.getElementById("pwd-reset-token-input");
  const passInput = document.getElementById("pwd-reset-new-password");
  const btn = document.getElementById("btn-confirm-reset");
  const resultEl = document.getElementById("pwd-reset-confirm-result");
  const token = tokenInput ? tokenInput.value.trim() : "";
  const newPassword = passInput ? passInput.value.trim() : "";

  if (!token) {
    toast("Enter the reset token", "error");
    return;
  }
  if (!newPassword || newPassword.length < 8) {
    toast("Password must be at least 8 characters", "error");
    return;
  }

  if (btn) {
    btn.disabled = true;
    btn.textContent = "Resetting…";
  }

  try {
    const res = await apiFetch("/api/saas/password-reset/reset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token, new_password: newPassword }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Reset failed");

    if (resultEl) {
      resultEl.textContent = data.message || "Password has been reset successfully!";
      resultEl.className = "pwd-reset-result success";
      resultEl.classList.remove("hidden");
    }
    toast("Password reset successfully!", "success");

    // Clear the form
    if (tokenInput) tokenInput.value = "";
    if (passInput) passInput.value = "";
  } catch (err) {
    if (resultEl) {
      resultEl.textContent = err.message;
      resultEl.className = "pwd-reset-result error";
      resultEl.classList.remove("hidden");
    }
    toast(`Error: ${err.message}`, "error");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "Reset Password";
    }
  }
}
