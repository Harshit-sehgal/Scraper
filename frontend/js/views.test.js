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
  setEngineStatus: vi.fn(),
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
    <div id="nav-jobs" class="nav-item">Jobs</div>
    <div id="nav-new" class="nav-item">New</div>
    <div id="nav-recycle" class="nav-item">Recycle</div>
    <div id="nav-cognition" class="nav-item">Cognition</div>
    <div id="nav-dashboard" class="nav-item">Dashboard</div>
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
  it("starts with dashboard view and manual mode", () => {
    expect(currentView).toBe("dashboard");
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
    expect(document.getElementById("nav-new").classList.contains("active")).toBe(true);
    expect(document.getElementById("nav-jobs").classList.contains("active")).toBe(false);
  });

  it("deactivates all views and tabs before activating the target", () => {
    switchView("jobs");
    switchView("dashboard");
    expect(document.getElementById("view-dashboard").classList.contains("active")).toBe(true);
    expect(document.getElementById("view-jobs").classList.contains("active")).toBe(false);
    expect(document.getElementById("nav-dashboard").classList.contains("active")).toBe(true);
    expect(document.getElementById("nav-jobs").classList.contains("active")).toBe(false);
  });

  it("updates currentView state", () => {
    switchView("recycle");
    expect(currentView).toBe("recycle");
  });

  it("highlights the workflows tab when switching to workflows", () => {
    document.body.innerHTML += `
      <section class="view" id="view-workflows"></section>
      <div id="nav-workflows" class="nav-item">Workflows</div>
    `;
    switchView("workflows");
    expect(document.getElementById("nav-workflows").classList.contains("active")).toBe(true);
  });

  it("highlights the billing tab when switching to billing", () => {
    document.body.innerHTML += `
      <section class="view" id="view-billing"></section>
      <div id="nav-billing" class="nav-item">Billing</div>
    `;
    switchView("billing");
    expect(document.getElementById("nav-billing").classList.contains("active")).toBe(true);
  });

  it("highlights the audit tab when switching to audit", () => {
    document.body.innerHTML += `
      <section class="view" id="view-audit"></section>
      <div id="nav-audit" class="nav-item">Audit</div>
    `;
    switchView("audit");
    expect(document.getElementById("nav-audit").classList.contains("active")).toBe(true);
  });

  it("highlights the retention tab when switching to retention", () => {
    document.body.innerHTML += `
      <section class="view" id="view-retention"></section>
      <div id="nav-retention" class="nav-item">Retention</div>
    `;
    switchView("retention");
    expect(document.getElementById("nav-retention").classList.contains("active")).toBe(true);
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

  it('key "3" switches to dashboard view', () => {
    const e = new KeyboardEvent("keydown", { key: "3" });
    e.preventDefault = vi.fn();
    onGlobalKeydown(e);
    expect(e.preventDefault).toHaveBeenCalled();
    expect(document.getElementById("view-dashboard").classList.contains("active")).toBe(true);
  });

  it('key "8" switches to billing view', () => {
    document.body.innerHTML += '<section class="view" id="view-billing"></section>';
    const e = new KeyboardEvent("keydown", { key: "8" });
    e.preventDefault = vi.fn();
    onGlobalKeydown(e);
    expect(e.preventDefault).toHaveBeenCalled();
    expect(document.getElementById("view-billing").classList.contains("active")).toBe(true);
  });

  it('key "9" switches to audit view', () => {
    document.body.innerHTML += '<section class="view" id="view-audit"></section>';
    const e = new KeyboardEvent("keydown", { key: "9" });
    e.preventDefault = vi.fn();
    onGlobalKeydown(e);
    expect(e.preventDefault).toHaveBeenCalled();
    expect(document.getElementById("view-audit").classList.contains("active")).toBe(true);
  });

  it('key "0" switches to retention view', () => {
    document.body.innerHTML += '<section class="view" id="view-retention"></section>';
    const e = new KeyboardEvent("keydown", { key: "0" });
    e.preventDefault = vi.fn();
    onGlobalKeydown(e);
    expect(e.preventDefault).toHaveBeenCalled();
    expect(document.getElementById("view-retention").classList.contains("active")).toBe(true);
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
