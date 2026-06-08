/* ═══════════════════════════════════════════
   DataForge — Utility Functions
   ═══════════════════════════════════════════ */

// ─── HTML Escaping ───

export function esc(s) {
  if (s === null || s === undefined) return "";
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

export function attrStr(s) {
  if (s === null || s === undefined) return "";
  if (typeof s !== "string") s = String(s);
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// ─── Toast Notifications ───

export function toast(msg, type = "info", duration = 3000) {
  const c = document.getElementById("toasts");
  if (!c) return;

  // Limit visible toasts to prevent DOM bloat
  const MAX_TOASTS = 5;
  while (c.children.length >= MAX_TOASTS) {
    c.firstChild.remove();
  }

  const t = document.createElement("div");
  t.className = `toast ${type}`;

  // Message content
  const msgSpan = document.createElement("span");
  msgSpan.textContent = msg;
  t.appendChild(msgSpan);

  // Auto-dismiss timer bar
  const timer = document.createElement("div");
  timer.className = "toast-timer";
  timer.style.animationDuration = `${duration}ms`;
  t.appendChild(timer);

  c.appendChild(t);

  // Auto-dismiss with animation
  const dismissTimeout = setTimeout(() => {
    t.classList.add("dismissing");
    setTimeout(() => {
      if (t.parentNode) t.remove();
    }, 200);
  }, duration);

  // Allow click-to-dismiss
  t.addEventListener("click", () => {
    clearTimeout(dismissTimeout);
    t.classList.add("dismissing");
    setTimeout(() => {
      if (t.parentNode) t.remove();
    }, 200);
  });

  return t;
}

// ─── Engine Status ───

export function setEngineStatus(text, offline = false) {
  const el = document.getElementById("engine-status");
  const textEl = document.getElementById("engine-status-text");
  if (!el || !textEl) return;
  textEl.textContent = text;
  el.classList.toggle("offline", offline);
}

export function setEnginePolling(active) {
  const el = document.getElementById("engine-status");
  if (!el) return;
  const dot = el.querySelector(".dot");
  if (!dot) return;
  dot.classList.toggle("polling", active);
}

// ─── Dark Mode ───

const THEME_KEY = "dataforge_theme_v1";

export function initTheme() {
  const preferred = localStorage.getItem(THEME_KEY);
  if (preferred) {
    // User explicitly set a preference — use it
    if (preferred === "dark") {
      document.documentElement.setAttribute("data-theme", "dark");
      updateThemeToggleIcon("dark");
    } else {
      document.documentElement.removeAttribute("data-theme");
      updateThemeToggleIcon("light");
    }
  } else {
    // No explicit preference — follow system
    applySystemTheme();
    // Listen for OS-level theme changes
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    mq.addEventListener("change", (e) => {
      if (!localStorage.getItem(THEME_KEY)) {
        applySystemTheme();
      }
    });
  }
}

function applySystemTheme() {
  const isDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  if (isDark) {
    document.documentElement.setAttribute("data-theme", "dark");
    updateThemeToggleIcon("dark");
  } else {
    document.documentElement.removeAttribute("data-theme");
    updateThemeToggleIcon("light");
  }
}

export function toggleTheme() {
  const isDark = document.documentElement.getAttribute("data-theme") === "dark";
  if (isDark) {
    document.documentElement.removeAttribute("data-theme");
    try {
      localStorage.setItem(THEME_KEY, "light");
    } catch {
      /* private browsing */
    }
    updateThemeToggleIcon("light");
    toast("Light mode", "info");
  } else {
    document.documentElement.setAttribute("data-theme", "dark");
    try {
      localStorage.setItem(THEME_KEY, "dark");
    } catch {
      /* private browsing */
    }
    updateThemeToggleIcon("dark");
    toast("Dark mode", "info");
  }
}

function updateThemeToggleIcon(theme) {
  const btn = document.getElementById("btn-theme-toggle");
  if (!btn) return;
  btn.textContent = theme === "dark" ? "☀️" : "🌙";
}

// ─── Shortcut Help Modal ───

function getFocusableIn(root) {
  if (!root) return [];
  const sel =
    'a[href], area[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
  return Array.from(root.querySelectorAll(sel)).filter((el) => {
    if (el.hasAttribute("hidden")) return false;
    const rects = el.getClientRects();
    return rects.length > 0;
  });
}

let _activeFocusTrap = null;

function attachFocusTrap(overlay) {
  if (!overlay) return;
  detachFocusTrap();
  const handler = (e) => {
    if (e.key !== "Tab") return;
    const items = getFocusableIn(overlay);
    if (!items.length) {
      e.preventDefault();
      return;
    }
    const first = items[0];
    const last = items[items.length - 1];
    const active = document.activeElement;
    if (e.shiftKey) {
      if (active === first || !overlay.contains(active)) {
        e.preventDefault();
        last.focus();
      }
    } else {
      if (active === last || !overlay.contains(active)) {
        e.preventDefault();
        first.focus();
      }
    }
  };
  overlay.addEventListener("keydown", handler);
  _activeFocusTrap = { overlay, handler };
}

function detachFocusTrap() {
  if (_activeFocusTrap) {
    _activeFocusTrap.overlay.removeEventListener("keydown", _activeFocusTrap.handler);
    _activeFocusTrap = null;
  }
}

export function showShortcuts() {
  const overlay = document.getElementById("shortcut-overlay");
  if (overlay) {
    overlay.classList.remove("hidden");
    attachFocusTrap(overlay);
    const closeBtn = overlay.querySelector("button");
    if (closeBtn) setTimeout(() => closeBtn.focus(), 50);
  }
}

export function hideShortcuts() {
  const overlay = document.getElementById("shortcut-overlay");
  if (overlay) overlay.classList.add("hidden");
  detachFocusTrap();
}

export function attachFocusTrapTo(overlay) {
  attachFocusTrap(overlay);
}

export function detachFocusTrapFrom() {
  detachFocusTrap();
}

export function isShortcutsVisible() {
  const overlay = document.getElementById("shortcut-overlay");
  return !!(overlay && !overlay.classList.contains("hidden"));
}

// ─── UI State Persistence ───

const UI_STATE_KEY = "dataforge_ui_state_v1";

export function readUIState() {
  try {
    const raw = localStorage.getItem(UI_STATE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

export function writeUIState(patch) {
  try {
    const next = { ...readUIState(), ...(patch || {}) };
    localStorage.setItem(UI_STATE_KEY, JSON.stringify(next));
  } catch {
    // Ignore storage errors (private mode, quota, etc.)
  }
}

// ─── Jobs Last Updated Label ───

let jobsUpdatedAt = 0;

export function getJobsUpdatedAt() {
  return jobsUpdatedAt;
}

export function setJobsUpdatedAt(ts) {
  jobsUpdatedAt = ts;
}

export function updateJobsLastUpdatedLabel(forceText = "") {
  const el = document.getElementById("jobs-last-updated");
  if (!el) return;

  if (forceText) {
    el.textContent = forceText;
    return;
  }

  if (!jobsUpdatedAt) {
    el.textContent = "Never updated";
    return;
  }

  const diffSec = Math.max(0, Math.floor((Date.now() - jobsUpdatedAt) / 1000));
  if (diffSec < 5) {
    el.textContent = "Updated just now";
    return;
  }
  if (diffSec < 60) {
    el.textContent = `Updated ${diffSec}s ago`;
    return;
  }
  const mins = Math.floor(diffSec / 60);
  el.textContent = `Updated ${mins}m ago`;
}

// ─── Confirmation Modal ───

let _pendingConfirm = null;

export function showConfirm(title, description, onConfirm) {
  const overlay = document.getElementById("confirm-overlay");
  const titleEl = document.getElementById("confirm-modal-title");
  const descEl = document.getElementById("confirm-modal-desc");
  if (!overlay || !titleEl || !descEl) return;

  titleEl.textContent = title;
  descEl.textContent = description;
  overlay.classList.remove("hidden");
  _pendingConfirm = onConfirm || null;

  attachFocusTrap(overlay);

  // Focus the cancel button by default (safer)
  const cancelBtn = document.getElementById("btn-confirm-cancel");
  if (cancelBtn) setTimeout(() => cancelBtn.focus(), 50);
}

export function closeConfirm() {
  const overlay = document.getElementById("confirm-overlay");
  if (overlay) overlay.classList.add("hidden");
  _pendingConfirm = null;
  detachFocusTrap();
}

export function executeConfirm() {
  if (typeof _pendingConfirm === "function") {
    const fn = _pendingConfirm;
    _pendingConfirm = null;
    closeConfirm();
    fn();
  }
}

export function isConfirmVisible() {
  const overlay = document.getElementById("confirm-overlay");
  return !!(overlay && !overlay.classList.contains("hidden"));
}

// ─── Keyboard Helpers ───

export function isTypingTarget(target) {
  if (!target) return false;
  const tag = String(target.tagName || "").toLowerCase();
  // isContentEditable is a boolean read-only property available in
  // real browsers. In jsdom the property is undefined, so we also
  // check the reflected contenteditable attribute as a fallback.
  return !!(
    tag === "input" ||
    tag === "textarea" ||
    tag === "select" ||
    target.isContentEditable ||
    target.getAttribute?.("contenteditable") === "true"
  );
}
