import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import {
  esc,
  attrStr,
  toast,
  setEngineStatus,
  setEnginePolling,
  initTheme,
  toggleTheme,
  showShortcuts,
  hideShortcuts,
  isShortcutsVisible,
  attachFocusTrapTo,
  detachFocusTrapFrom,
  showConfirm,
  closeConfirm,
  executeConfirm,
  isConfirmVisible,
  readUIState,
  writeUIState,
  getJobsUpdatedAt,
  setJobsUpdatedAt,
  updateJobsLastUpdatedLabel,
  isTypingTarget,
} from "./utils.js";

describe("esc()", () => {
  it("escapes HTML special characters", () => {
    const result = esc('<script>alert("xss")</script>');
    // jsdom encodes < > but not double quotes (they don't need
    // escaping in HTML text nodes per spec).
    expect(result).toContain("&lt;script&gt;");
    expect(result).toContain("&lt;/script&gt;");
    expect(result).not.toContain("<script>");
  });

  it("returns empty string for empty input", () => {
    expect(esc("")).toBe("");
  });

  it("handles plain strings unchanged", () => {
    expect(esc("hello world")).toBe("hello world");
  });

  it("escapes & symbol", () => {
    expect(esc("a & b")).toBe("a &amp; b");
  });
});

describe("toast()", () => {
  beforeEach(() => {
    // Create toasts container
    const container = document.createElement("div");
    container.id = "toasts";
    document.body.appendChild(container);
  });

  afterEach(() => {
    const container = document.getElementById("toasts");
    if (container) container.remove();
  });

  it("creates a toast element with correct type class", () => {
    const el = toast("Test message", "success");
    expect(el).toBeDefined();
    expect(el.className).toContain("toast");
    expect(el.className).toContain("success");
  });

  it("sets text content of the message", () => {
    const el = toast("Hello world", "info");
    const msgSpan = el.querySelector("span");
    expect(msgSpan.textContent).toBe("Hello world");
  });

  it("adds timer bar element", () => {
    const el = toast("Timed", "info", 5000);
    const timer = el.querySelector(".toast-timer");
    expect(timer).toBeDefined();
    expect(timer.style.animationDuration).toBe("5000ms");
  });

  it("returns undefined when container does not exist", () => {
    document.getElementById("toasts").remove();
    const el = toast("Nowhere");
    expect(el).toBeUndefined();
  });
});

describe("setEngineStatus()", () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <div id="engine-status">
        <span class="dot"></span>
        <span id="engine-status-text"></span>
      </div>
    `;
  });

  it("updates the status text", () => {
    setEngineStatus("Running", false);
    const textEl = document.getElementById("engine-status-text");
    expect(textEl.textContent).toBe("Running");
  });

  it("toggles offline class", () => {
    setEngineStatus("Offline", true);
    const el = document.getElementById("engine-status");
    expect(el.classList.contains("offline")).toBe(true);
  });

  it("removes offline class when online", () => {
    setEngineStatus("Offline", true);
    setEngineStatus("Online", false);
    const el = document.getElementById("engine-status");
    expect(el.classList.contains("offline")).toBe(false);
  });
});

describe("setEnginePolling()", () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <div id="engine-status">
        <span class="dot"></span>
        <span id="engine-status-text"></span>
      </div>
    `;
  });

  it("adds polling class when active", () => {
    setEnginePolling(true);
    const dot = document.querySelector("#engine-status .dot");
    expect(dot.classList.contains("polling")).toBe(true);
  });

  it("removes polling class when inactive", () => {
    setEnginePolling(true);
    setEnginePolling(false);
    const dot = document.querySelector("#engine-status .dot");
    expect(dot.classList.contains("polling")).toBe(false);
  });
});

// ─── attrStr ───────────────────────────────────────────────────────────────

describe("attrStr()", () => {
  it("escapes & < > \" and '", () => {
    const result = attrStr('<a href="test&">');
    expect(result).toBe("&lt;a href=&quot;test&amp;&quot;&gt;");
  });

  it("returns empty string for null", () => {
    expect(attrStr(null)).toBe("");
  });

  it("returns empty string for undefined", () => {
    expect(attrStr(undefined)).toBe("");
  });

  it("converts numbers to strings", () => {
    expect(attrStr(42)).toBe("42");
  });

  it("passes through plain strings unchanged", () => {
    expect(attrStr("hello world")).toBe("hello world");
  });
});

// ─── Theme ─────────────────────────────────────────────────────────────────

describe("theme helpers", () => {
  const THEME_KEY = "dataforge_theme_v1";

  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
    // Set up theme toggle button in DOM
    const btn = document.createElement("button");
    btn.id = "btn-theme-toggle";
    btn.textContent = "🌙";
    document.body.appendChild(btn);
    // Set up the #toasts container for toggleTheme
    const toasts = document.createElement("div");
    toasts.id = "toasts";
    document.body.appendChild(toasts);
  });

  afterEach(() => {
    const btn = document.getElementById("btn-theme-toggle");
    if (btn) btn.remove();
    const toasts = document.getElementById("toasts");
    if (toasts) toasts.remove();
  });

  it("initTheme follows system preference when no saved theme", () => {
    // jsdom does not implement window.matchMedia; we mock a stub so
    // applySystemTheme does not throw.
    const orig = window.matchMedia;
    window.matchMedia = () => ({ matches: false, addEventListener: () => {} });
    try {
      initTheme();
      // System preference is mocked to "light" — no data-theme attr
      expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
      expect(localStorage.getItem(THEME_KEY)).toBeNull();
    } finally {
      window.matchMedia = orig;
    }
  });

  it("initTheme restores saved dark theme", () => {
    localStorage.setItem(THEME_KEY, "dark");
    initTheme();
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(document.getElementById("btn-theme-toggle").textContent).toBe("☀️");
  });

  it("initTheme restores saved light theme", () => {
    localStorage.setItem(THEME_KEY, "light");
    initTheme();
    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
    expect(document.getElementById("btn-theme-toggle").textContent).toBe("🌙");
  });

  it("toggleTheme switches from light to dark", () => {
    toggleTheme();
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(localStorage.getItem(THEME_KEY)).toBe("dark");
    expect(document.getElementById("btn-theme-toggle").textContent).toBe("☀️");
  });

  it("toggleTheme switches from dark to light", () => {
    document.documentElement.setAttribute("data-theme", "dark");
    toggleTheme();
    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
    expect(localStorage.getItem(THEME_KEY)).toBe("light");
    expect(document.getElementById("btn-theme-toggle").textContent).toBe("🌙");
  });
});

// ─── Shortcuts ─────────────────────────────────────────────────────────────

describe("shortcuts modal", () => {
  beforeEach(() => {
    const overlay = document.createElement("div");
    overlay.id = "shortcut-overlay";
    overlay.className = "hidden";
    overlay.innerHTML = '<button id="shortcut-close">Close</button>';
    document.body.appendChild(overlay);
  });

  afterEach(() => {
    const overlay = document.getElementById("shortcut-overlay");
    if (overlay) overlay.remove();
  });

  it("showShortcuts removes hidden class and attaches focus trap", () => {
    showShortcuts();
    const overlay = document.getElementById("shortcut-overlay");
    expect(overlay.classList.contains("hidden")).toBe(false);
    expect(isShortcutsVisible()).toBe(true);
  });

  it("hideShortcuts adds hidden class and detaches focus trap", () => {
    showShortcuts();
    hideShortcuts();
    const overlay = document.getElementById("shortcut-overlay");
    expect(overlay.classList.contains("hidden")).toBe(true);
    expect(isShortcutsVisible()).toBe(false);
  });

  it("isShortcutsVisible returns false when overlay is missing", () => {
    document.getElementById("shortcut-overlay").remove();
    expect(isShortcutsVisible()).toBe(false);
  });

  it("attachFocusTrapTo and detachFocusTrapFrom do not throw", () => {
    const el = document.createElement("div");
    attachFocusTrapTo(el);
    detachFocusTrapFrom();
    // No assertion needed — just verify no error
  });
});

// ─── Confirm Modal ─────────────────────────────────────────────────────────

describe("confirm modal", () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <div id="confirm-overlay" class="hidden">
        <div id="confirm-modal">
          <h3 id="confirm-modal-title"></h3>
          <p id="confirm-modal-desc"></p>
          <button id="btn-confirm-confirm">Confirm</button>
          <button id="btn-confirm-cancel">Cancel</button>
        </div>
      </div>
    `;
  });

  it("showConfirm shows overlay and sets title/description", () => {
    showConfirm("Delete job?", "This will remove the job permanently.", null);
    const overlay = document.getElementById("confirm-overlay");
    expect(overlay.classList.contains("hidden")).toBe(false);
    expect(document.getElementById("confirm-modal-title").textContent).toBe("Delete job?");
    expect(document.getElementById("confirm-modal-desc").textContent).toBe("This will remove the job permanently.");
  });

  it("closeConfirm hides overlay", () => {
    showConfirm("Test", "Desc", null);
    closeConfirm();
    expect(document.getElementById("confirm-overlay").classList.contains("hidden")).toBe(true);
    expect(isConfirmVisible()).toBe(false);
  });

  it("executeConfirm calls the callback and hides overlay", () => {
    const fn = vi.fn();
    showConfirm("Test", "Desc", fn);
    executeConfirm();
    expect(fn).toHaveBeenCalledOnce();
    expect(document.getElementById("confirm-overlay").classList.contains("hidden")).toBe(true);
  });

  it("executeConfirm does not throw when no callback set", () => {
    showConfirm("Test", "Desc", null);
    expect(() => executeConfirm()).not.toThrow();
  });

  it("isConfirmVisible returns false when overlay is missing", () => {
    document.getElementById("confirm-overlay").remove();
    expect(isConfirmVisible()).toBe(false);
  });
});

// ─── UI State Persistence ─────────────────────────────────────────────────

describe("UI state persistence", () => {
  const UI_STATE_KEY = "dataforge_ui_state_v1";

  beforeEach(() => {
    localStorage.clear();
  });

  it("readUIState returns empty object when nothing stored", () => {
    expect(readUIState()).toEqual({});
  });

  it("readUIState returns parsed data", () => {
    localStorage.setItem(UI_STATE_KEY, JSON.stringify({ tab: "dashboard", theme: "dark" }));
    expect(readUIState()).toEqual({ tab: "dashboard", theme: "dark" });
  });

  it("writeUIState merges with existing state", () => {
    writeUIState({ tab: "recycle" });
    writeUIState({ filter: "failed" });
    const state = readUIState();
    expect(state.tab).toBe("recycle");
    expect(state.filter).toBe("failed");
  });

  it("writeUIState overwrites existing keys", () => {
    writeUIState({ tab: "recycle" });
    writeUIState({ tab: "dashboard" });
    expect(readUIState().tab).toBe("dashboard");
  });

  it("readUIState returns empty object on corrupt JSON", () => {
    localStorage.setItem(UI_STATE_KEY, "{invalid json}");
    expect(readUIState()).toEqual({});
  });
});

// ─── Jobs Last Updated ─────────────────────────────────────────────────────

describe("jobs last updated label", () => {
  beforeEach(() => {
    setJobsUpdatedAt(0);
    const el = document.createElement("span");
    el.id = "jobs-last-updated";
    document.body.appendChild(el);
  });

  afterEach(() => {
    const el = document.getElementById("jobs-last-updated");
    if (el) el.remove();
  });

  it("shows 'Never updated' when no timestamp set", () => {
    updateJobsLastUpdatedLabel();
    expect(document.getElementById("jobs-last-updated").textContent).toBe("Never updated");
  });

  it("shows 'Updated just now' for recent timestamp", () => {
    setJobsUpdatedAt(Date.now());
    updateJobsLastUpdatedLabel();
    expect(document.getElementById("jobs-last-updated").textContent).toBe("Updated just now");
  });

  it("forces custom text when forceText provided", () => {
    updateJobsLastUpdatedLabel("Refreshing...");
    expect(document.getElementById("jobs-last-updated").textContent).toBe("Refreshing...");
  });

  it("shows seconds when under 60s", () => {
    setJobsUpdatedAt(Date.now() - 30000);
    updateJobsLastUpdatedLabel();
    const text = document.getElementById("jobs-last-updated").textContent;
    expect(text).toMatch(/^Updated \d+s ago$/);
  });

  it("tracks getJobsUpdatedAt after setJobsUpdatedAt", () => {
    const ts = Date.now() - 10000;
    setJobsUpdatedAt(ts);
    expect(getJobsUpdatedAt()).toBe(ts);
  });
});

// ─── isTypingTarget ────────────────────────────────────────────────────────

describe("isTypingTarget()", () => {
  it("returns true for input elements", () => {
    const el = document.createElement("input");
    expect(isTypingTarget(el)).toBe(true);
  });

  it("returns true for textarea elements", () => {
    const el = document.createElement("textarea");
    expect(isTypingTarget(el)).toBe(true);
  });

  it("returns true for select elements", () => {
    const el = document.createElement("select");
    expect(isTypingTarget(el)).toBe(true);
  });

  it("returns true for contentEditable elements", () => {
    const el = document.createElement("div");
    // Some jsdom versions reflect the attribute; set both to be safe.
    el.setAttribute("contenteditable", "true");
    el.contentEditable = "true";
    expect(isTypingTarget(el)).toBe(true);
  });

  it("returns false for button elements", () => {
    const el = document.createElement("button");
    expect(isTypingTarget(el)).toBe(false);
  });

  it("returns false for null", () => {
    expect(isTypingTarget(null)).toBe(false);
  });
});
