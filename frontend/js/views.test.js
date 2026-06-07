import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";

import {
  currentView,
  currentMode,
  setCurrentView,
  setCurrentMode,
  switchView,
  setMode,
  onGlobalKeydown,
} from "./views.js";

// Mock utils.js at the top level (vitest hoists vi.mock calls)
vi.mock("./utils.js", () => ({
  writeUIState: vi.fn(),
  isTypingTarget: vi.fn(() => false),
  showShortcuts: vi.fn(),
  hideShortcuts: vi.fn(),
  isShortcutsVisible: vi.fn(() => false),
  closeConfirm: vi.fn(),
  isConfirmVisible: vi.fn(() => false),
}));

// Import mocked utils after vi.mock so we get the mock implementations
import { showShortcuts as mockedShowShortcuts, isTypingTarget as mockedIsTypingTarget } from "./utils.js";

// ─── Helpers ────────────────────────────────────────────────────────────

function setupDOM() {
  document.body.innerHTML = `
    <div id="view-jobs" class="view">Jobs</div>
    <div id="view-new" class="view">New Job</div>
    <div id="view-results" class="view">Results</div>
    <div id="view-recycle" class="view">Recycle Bin</div>
    <div id="view-cognition" class="view">Cognition</div>
    <div id="view-dashboard" class="view">Dashboard</div>
    <div id="tab-jobs" class="tab">Jobs</div>
    <div id="tab-new" class="tab">New</div>
    <div id="tab-recycle" class="tab">Recycle</div>
    <div id="tab-cognition" class="tab">Cognition</div>
    <div id="tab-dashboard" class="tab">Dashboard</div>
    <div id="mode-toggle">
      <span class="toggle" data-mode="manual">Manual</span>
      <span class="toggle" data-mode="auto">Auto</span>
    </div>
    <div id="section-manual">Manual section</div>
    <div id="section-auto">Auto section</div>
    <input id="jobs-search" type="text" />
  `;
}

// ═══════════════════════════════════════════════════════════════════════
// State management
// ═══════════════════════════════════════════════════════════════════════

describe("view state management", () => {
  it("starts with jobs view and manual mode", () => {
    expect(currentView).toBe("jobs");
    expect(currentMode).toBe("manual");
  });

  it("setCurrentView updates the view name", () => {
    setCurrentView("new");
    expect(currentView).toBe("new");
    setCurrentView("jobs");
  });

  it("setCurrentMode updates the mode", () => {
    setCurrentMode("auto");
    expect(currentMode).toBe("auto");
    setCurrentMode("manual");
  });
});

// ═══════════════════════════════════════════════════════════════════════
// switchView
// ═══════════════════════════════════════════════════════════════════════

describe("switchView()", () => {
  beforeEach(() => {
    setupDOM();
  });

  it("activates the correct view and tab", () => {
    switchView("new");
    expect(document.getElementById("view-new").classList.contains("active")).toBe(true);
    expect(document.getElementById("view-jobs").classList.contains("active")).toBe(false);
    expect(document.getElementById("tab-new").classList.contains("active")).toBe(true);
    expect(document.getElementById("tab-jobs").classList.contains("active")).toBe(false);
  });

  it("deactivates all views and tabs before activating the target", () => {
    switchView("jobs");
    switchView("dashboard");
    expect(document.getElementById("view-dashboard").classList.contains("active")).toBe(true);
    expect(document.getElementById("view-jobs").classList.contains("active")).toBe(false);
    expect(document.getElementById("tab-dashboard").classList.contains("active")).toBe(true);
    expect(document.getElementById("tab-jobs").classList.contains("active")).toBe(false);
  });

  it("updates currentView state", () => {
    switchView("recycle");
    expect(currentView).toBe("recycle");
  });
});

// ═══════════════════════════════════════════════════════════════════════
// setMode
// ═══════════════════════════════════════════════════════════════════════

describe("setMode()", () => {
  beforeEach(() => {
    setupDOM();
  });

  it("toggles to auto mode", () => {
    setMode("auto");
    expect(currentMode).toBe("auto");
    const toggles = document.querySelectorAll("#mode-toggle .toggle");
    expect(toggles[0].classList.contains("active")).toBe(false);
    expect(toggles[1].classList.contains("active")).toBe(true);
    expect(document.getElementById("section-manual").classList.contains("hidden")).toBe(true);
    expect(document.getElementById("section-auto").classList.contains("hidden")).toBe(false);
  });

  it("toggles to manual mode", () => {
    setMode("auto");
    setMode("manual");
    expect(currentMode).toBe("manual");
    const toggles = document.querySelectorAll("#mode-toggle .toggle");
    expect(toggles[0].classList.contains("active")).toBe(true);
    expect(toggles[1].classList.contains("active")).toBe(false);
    expect(document.getElementById("section-manual").classList.contains("hidden")).toBe(false);
    expect(document.getElementById("section-auto").classList.contains("hidden")).toBe(true);
  });
});

// ═══════════════════════════════════════════════════════════════════════
// Global Keyboard Handler
// ═══════════════════════════════════════════════════════════════════════

describe("onGlobalKeydown()", () => {
  beforeEach(() => {
    setupDOM();
  });

  it('key "2" switches to new job view', () => {
    const e = new KeyboardEvent("keydown", { key: "2" });
    e.preventDefault = vi.fn();
    onGlobalKeydown(e);
    expect(e.preventDefault).toHaveBeenCalled();
    expect(document.getElementById("view-new").classList.contains("active")).toBe(true);
  });

  it('key "1" switches to jobs view', () => {
    switchView("new");
    const e = new KeyboardEvent("keydown", { key: "1" });
    e.preventDefault = vi.fn();
    onGlobalKeydown(e);
    expect(e.preventDefault).toHaveBeenCalled();
    expect(document.getElementById("view-jobs").classList.contains("active")).toBe(true);
  });

  it('key "5" switches to dashboard view', () => {
    const e = new KeyboardEvent("keydown", { key: "5" });
    e.preventDefault = vi.fn();
    onGlobalKeydown(e);
    expect(e.preventDefault).toHaveBeenCalled();
    expect(document.getElementById("view-dashboard").classList.contains("active")).toBe(true);
  });

  it('key "n" switches to new view', () => {
    document.body.innerHTML += '<input id="inp-name" type="text" />';
    const e = new KeyboardEvent("keydown", { key: "n" });
    e.preventDefault = vi.fn();
    onGlobalKeydown(e);
    expect(e.preventDefault).toHaveBeenCalled();
    expect(document.getElementById("view-new").classList.contains("active")).toBe(true);
  });

  it('key "/" focuses jobs search input', () => {
    const e = new KeyboardEvent("keydown", { key: "/" });
    e.preventDefault = vi.fn();
    onGlobalKeydown(e);
    expect(e.preventDefault).toHaveBeenCalled();
    expect(document.activeElement).toBe(document.getElementById("jobs-search"));
  });

  it('key "?" shows shortcuts modal', () => {
    const e = new KeyboardEvent("keydown", { key: "?" });
    e.preventDefault = vi.fn();
    onGlobalKeydown(e);
    expect(e.preventDefault).toHaveBeenCalled();
    expect(mockedShowShortcuts).toHaveBeenCalled();
  });

  it("does not respond to number keys when typing", () => {
    mockedIsTypingTarget.mockReturnValue(true);
    const e = new KeyboardEvent("keydown", { key: "2" });
    e.preventDefault = vi.fn();
    onGlobalKeydown(e);
    expect(e.preventDefault).not.toHaveBeenCalled();
  });

  it("Escape clears jobs search when focused", () => {
    document.getElementById("jobs-search").value = "test";
    document.getElementById("jobs-search").focus();
    const e = new KeyboardEvent("keydown", { key: "Escape" });
    e.preventDefault = vi.fn();
    onGlobalKeydown(e);
    expect(e.preventDefault).toHaveBeenCalled();
    expect(document.getElementById("jobs-search").value).toBe("");
  });
});
