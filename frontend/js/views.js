/* ═══════════════════════════════════════════
   DataForge — View Management
   ═══════════════════════════════════════════ */

import {
  writeUIState,
  isTypingTarget,
  showShortcuts,
  hideShortcuts,
  isShortcutsVisible,
  closeConfirm,
  isConfirmVisible,
} from "./utils.js";
import { refreshJobs, onJobsFilterChanged } from "./jobs.js";
import { renderFilteredResults } from "./results.js";

export let currentView = "jobs";
export let currentMode = "manual";

export function setCurrentView(name) {
  currentView = name;
}

export function setCurrentMode(mode) {
  currentMode = mode;
}

// ─── View / Tab Switching ───

export function switchView(name) {
  // H2: Programmatic guard — redirect cognition to jobs when experimental is off
  if (name === "cognition" && window.DATAFORGE_EXPERIMENTAL !== true) {
    name = "jobs";
  }
  currentView = name;
  document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
  document.querySelectorAll(".tab").forEach((t) => {
    t.classList.remove("active");
    t.setAttribute("aria-selected", "false");
  });
  const viewEl = document.getElementById(`view-${name}`);
  if (viewEl) viewEl.classList.add("active");

  const tabMap = {
    jobs: "tab-jobs",
    new: "tab-new",
    recycle: "tab-recycle",
    cognition: "tab-cognition",
    dashboard: "tab-dashboard",
  };
  const tabEl = document.getElementById(tabMap[name]);
  if (tabEl) {
    tabEl.classList.add("active");
    tabEl.setAttribute("aria-selected", "true");
  }

  if (name === "jobs") refreshJobs().catch(() => {});
  if (name === "new") import("./form.js").then((m) => m.initForm()).catch(() => {});
  if (name === "recycle") import("./recycle.js").then((m) => m.refreshRecycleBin()).catch(() => {});
  if (name === "cognition") import("./cognition.js").then((m) => m.refreshCognition()).catch(() => {});
  if (name === "dashboard") import("./dashboard.js").then((m) => m.refreshDashboard()).catch(() => {});

  writeUIState({ view: name });
}

// ─── Mode Toggle ───

export function setMode(mode) {
  currentMode = mode;
  document.querySelectorAll("#mode-toggle .toggle").forEach((t) => {
    t.classList.toggle("active", t.dataset.mode === mode);
  });
  const manualSection = document.getElementById("section-manual");
  if (manualSection) manualSection.classList.toggle("hidden", mode !== "manual");
  const autoSection = document.getElementById("section-auto");
  if (autoSection) autoSection.classList.toggle("hidden", mode !== "auto");
}

// ─── Global Keyboard Handler ───

const TAB_KEYS = {
  1: "jobs",
  2: "new",
  3: "recycle",
  4: "cognition",
  5: "dashboard",
};

export function onGlobalKeydown(e) {
  const typing = isTypingTarget(e.target);
  const jobsSearch = document.getElementById("jobs-search");
  const resultSearch = document.getElementById("inp-result-search");

  // Number keys 1-5: switch between tabs (only when not typing)
  if (!typing && e.key >= "1" && e.key <= "5") {
    // H2: Guard keyboard shortcut for cognition tab
    if (e.key === "4" && window.DATAFORGE_EXPERIMENTAL !== true) {
      return;
    }
    e.preventDefault();
    const viewName = TAB_KEYS[e.key];
    if (viewName) {
      switchView(viewName);
    }
    return;
  }

  if (!typing && e.key === "n") {
    e.preventDefault();
    switchView("new");
    const nameInput = document.getElementById("inp-name");
    if (nameInput) nameInput.focus();
    return;
  }

  if (!typing && e.key === "/") {
    e.preventDefault();
    const inResults = document.getElementById("view-results")?.classList.contains("active");
    const inNew = document.getElementById("view-new")?.classList.contains("active");
    const target = inResults ? resultSearch : inNew ? document.getElementById("inp-intent") : jobsSearch;
    if (target) {
      target.focus();
      target.select();
    }
    return;
  }

  if (e.key === "Escape") {
    // Close confirmation modal if open
    if (isConfirmVisible()) {
      closeConfirm();
      e.preventDefault();
      return;
    }

    // Close shortcuts modal if open
    if (isShortcutsVisible()) {
      hideShortcuts();
      e.preventDefault();
      return;
    }

    if (document.activeElement === jobsSearch && jobsSearch?.value) {
      jobsSearch.value = "";
      onJobsFilterChanged();
      e.preventDefault();
      return;
    }

    if (document.activeElement === resultSearch && resultSearch?.value) {
      resultSearch.value = "";
      renderFilteredResults();
      e.preventDefault();
    }
  }

  if (!typing && e.key === "?") {
    e.preventDefault();
    showShortcuts();
  }
}
