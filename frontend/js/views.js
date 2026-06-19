/* ═══════════════════════════════════════════
   DataForge — View Management + Client-side Router
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
import { hydrateIcons } from "./icons.js";

export let currentView = "jobs";
export let currentMode = "manual";

// Track the previously-shown view so switchView can stop per-view
// background timers (system-info / recent-activity polls) when the
// user leaves a view. Without this, those 30s/60s polls run forever
// after the first dashboard visit (F-008).
let _previousView = null;

export function setCurrentView(name) {
  currentView = name;
}

export function setCurrentMode(mode) {
  currentMode = mode;
}

// ─── Router ───

const VIEW_MAP = {
  "/": "jobs",
  "/jobs": "jobs",
  "/new": "new",
  "/recycle": "recycle",
  "/cognition": "cognition",
  "/dashboard": "dashboard",
  "/auth-profiles": "auth-profiles",
  "/workflows": "workflows",
  "/billing": "billing",
  "/audit": "audit",
  "/retention": "retention",
};

// Detect the SPA base path from the initial page load (e.g. /app/ or /)
function getBasePath() {
  const path = window.location.pathname;
  // If we're under /app/... or /app, treat /app as the base
  const appIndex = path.indexOf("/app");
  if (appIndex !== -1) return "/app";
  return "";
}

const BASE_PATH = getBasePath();

export function getViewFromPath(path) {
  // Strip base path (e.g. "/app/jobs" → "/jobs")
  const normalized = path.replace(BASE_PATH, "").replace(/\/+$/, "") || "/";
  return VIEW_MAP[normalized] || "jobs";
}

export function getPathFromView(view) {
  const suffix = view === "jobs" ? "/jobs" : `/${view}`;
  return BASE_PATH ? `${BASE_PATH}${suffix}` : suffix;
}

// ─── View / Tab Switching ───

export function switchView(name) {
  // H2: Programmatic guard — redirect cognition to jobs when experimental is off
  if (name === "cognition" && window.DATAFORGE_EXPERIMENTAL !== true) {
    name = "jobs";
  }
  // F-008: stop dashboard background polls when leaving the dashboard
  // so system-info (30s) and recent-activity (60s) timers don't run
  // forever after the first dashboard visit.
  if (_previousView === "dashboard" && name !== "dashboard") {
    import("./system-info.js").then((m) => m.stopSystemInfo?.()).catch(() => {});
    import("./recent-activity.js").then((m) => m.stopRecentActivity?.()).catch(() => {});
  }
  _previousView = currentView;
  currentView = name;

  // Update URL without full page reload
  const newPath = getPathFromView(name);
  if (window.location.pathname !== newPath) {
    window.history.pushState({ view: name }, "", newPath);
  }

  // Hide all views
  document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));

  // Update nav items (sidebar navigation)
  document.querySelectorAll(".nav-item").forEach((n) => {
    n.classList.remove("active");
  });

  const viewEl = document.getElementById(`view-${name}`);
  if (viewEl) viewEl.classList.add("active");

  // Close sidebar on mobile after navigating
  const sidebar = document.getElementById("sidebar");
  if (sidebar) sidebar.classList.remove("open");

  const navMap = {
    jobs: "nav-jobs",
    new: "nav-new",
    recycle: "nav-recycle",
    cognition: "nav-cognition",
    dashboard: "nav-dashboard",
    "auth-profiles": "nav-auth-profiles",
    workflows: "nav-workflows",
    billing: "nav-billing",
    audit: "nav-audit",
    retention: "nav-retention",
  };
  const navEl = document.getElementById(navMap[name]);
  if (navEl) {
    navEl.classList.add("active");
  }

  if (name === "jobs") refreshJobs().catch(() => {});
  if (name === "new") import("./form.js").then((m) => m.initForm()).catch(() => {});
  if (name === "recycle") import("./recycle.js").then((m) => m.refreshRecycleBin()).catch(() => {});
  if (name === "cognition") import("./cognition.js").then((m) => m.refreshCognition()).catch(() => {});
  if (name === "dashboard") {
    import("./dashboard.js").then((m) => m.refreshDashboard()).catch(() => {});
    import("./system-info.js").then((m) => m.startSystemInfo()).catch(() => {});
    import("./recent-activity.js").then((m) => m.startRecentActivity()).catch(() => {});
  }
  if (name === "auth-profiles") import("./auth-profiles.js").then((m) => m.refreshAuthProfiles()).catch(() => {});
  if (name === "workflows") import("./workflows.js").then((m) => m.refreshWorkflows()).catch(() => {});
  if (name === "billing") import("./billing.js").then((m) => m.refreshBilling()).catch(() => {});
  if (name === "audit") import("./audit.js").then((m) => m.refreshAudit()).catch(() => {});
  if (name === "retention") import("./retention.js").then((m) => m.refreshRetention()).catch(() => {});

  writeUIState({ view: name });

  // Hydrate [data-icon] placeholders in the newly-activated view
  requestAnimationFrame(() => hydrateIcons());
}

// ─── Popstate handler for back/forward buttons ───
window.addEventListener("popstate", () => {
  const path = window.location.pathname;
  const view = getViewFromPath(path);
  if (view && view !== currentView) {
    switchView(view);
  }
});

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
  6: "auth-profiles",
  7: "workflows",
  8: "billing",
  9: "audit",
  0: "retention",
};

export function onGlobalKeydown(e) {
  const typing = isTypingTarget(e.target);
  const jobsSearch = document.getElementById("jobs-search");
  const resultSearch = document.getElementById("inp-result-search");

  // Number keys 1-9, 0: switch between tabs (only when not typing)
  if (!typing && ((e.key >= "1" && e.key <= "9") || e.key === "0")) {
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
