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

export let currentView = "dashboard";
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
  "/": "dashboard",
  "/jobs": "jobs",
  "/new": "new",
  "/dashboard": "dashboard",
  "/api-keys": "api-keys",
  "/settings": "settings",
  "/recycle": "recycle",
  "/cognition": "cognition",
  "/auth-profiles": "auth-profiles",
  "/workflows": "workflows",
  "/billing": "billing",
  "/audit": "audit",
  "/retention": "retention",
  "/email-verification": "email-verification",
  "/password-reset": "password-reset",
  "/invitations": "invitations",
};

// Detect the SPA base path from the initial page load (e.g. /app/ or /)
// Guarded with typeof window check so this module can be imported in
// non-browser environments (Playwright, Node) without crashing.
function getBasePath() {
  if (typeof window === "undefined") return "";
  const path = window.location.pathname;
  // If we're under /app/... or /app, treat /app as the base
  const appIndex = path.indexOf("/app");
  return appIndex !== -1 ? "/app" : "";
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
    import("./system-info.js").then((m) => m.stopSystemInfo?.()).catch((e) => console.warn("Op:", e));
    import("./recent-activity.js").then((m) => m.stopRecentActivity?.()).catch((e) => console.warn("Op:", e));
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
    dashboard: "nav-dashboard",
    "api-keys": "nav-api-keys",
    settings: "nav-settings",
    recycle: "nav-recycle",
    cognition: "nav-cognition",
    "auth-profiles": "nav-auth-profiles",
    workflows: "nav-workflows",
    billing: "nav-billing",
    audit: "nav-audit",
    retention: "nav-retention",
    "email-verification": "nav-email-verification",
    "password-reset": "nav-password-reset",
    invitations: "nav-invitations",
  };
  const navEl = document.getElementById(navMap[name]);
  if (navEl) {
    navEl.classList.add("active");
    const parentDetails = navEl.closest("details");
    if (parentDetails) parentDetails.open = true;
  }

  if (name === "jobs") refreshJobs().catch((e) => console.warn("Op:", e));
  if (name === "new") import("./form.js").then((m) => m.initForm()).catch((e) => console.warn("Op:", e));
  if (name === "recycle")
    import("./recycle.js").then((m) => m.refreshRecycleBin()).catch((e) => console.warn("Op:", e));
  if (name === "cognition")
    import("./cognition.js").then((m) => m.refreshCognition()).catch((e) => console.warn("Op:", e));
  if (name === "dashboard") {
    import("./dashboard.js").then((m) => m.refreshDashboard()).catch((e) => console.warn("Op:", e));
    import("./system-info.js").then((m) => m.startSystemInfo()).catch((e) => console.warn("Op:", e));
    import("./recent-activity.js").then((m) => m.startRecentActivity()).catch((e) => console.warn("Op:", e));
  }
  if (name === "auth-profiles")
    import("./auth-profiles.js").then((m) => m.refreshAuthProfiles()).catch((e) => console.warn("Op:", e));
  if (name === "workflows")
    import("./workflows.js").then((m) => m.refreshWorkflows()).catch((e) => console.warn("Op:", e));
  if (name === "billing") import("./billing.js").then((m) => m.refreshBilling()).catch((e) => console.warn("Op:", e));
  if (name === "audit") import("./audit.js").then((m) => m.refreshAudit()).catch((e) => console.warn("Op:", e));
  if (name === "retention")
    import("./retention.js")
      .then((m) => {
        m.initRetention();
        m.refreshRetention();
      })
      .catch((e) => console.warn("Op:", e));
  if (name === "api-keys")
    import("./api-keys-page.js").then((m) => m.refreshApiKeysPage()).catch((e) => console.warn("Op:", e));
  if (name === "settings")
    import("./settings-page.js").then((m) => m.refreshSettingsPage()).catch((e) => console.warn("Op:", e));
  if (name === "email-verification")
    import("./email-verification.js").then((m) => m.refreshEmailVerification()).catch((e) => console.warn("Op:", e));
  if (name === "password-reset") {
    // No auto-refresh needed; form-based view
  }
  if (name === "invitations")
    import("./invitations.js").then((m) => m.refreshInvitations()).catch((e) => console.warn("Op:", e));

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
  3: "dashboard",
  4: "api-keys",
  5: "settings",
  6: "workflows",
  7: "auth-profiles",
  8: "billing",
  9: "audit",
  0: "retention",
  // Note: email-verification, password-reset, and invitations are
  // in the Account subnav and do not have dedicated number keys.
};

export function onGlobalKeydown(e) {
  const typing = isTypingTarget(e.target);
  const jobsSearch = document.getElementById("jobs-search");
  const resultSearch = document.getElementById("inp-result-search");

  // Cmd+K / Ctrl+K: open command palette
  if ((e.metaKey || e.ctrlKey) && e.key === "k") {
    e.preventDefault();
    import("./command-palette.js").then((m) => m.openCommandPalette()).catch((e) => console.warn("Op:", e));
    return;
  }

  // Number keys 1-9, 0: switch between tabs (only when not typing)
  if (!typing && ((e.key >= "1" && e.key <= "9") || e.key === "0")) {
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
    // Close command palette if open
    const cp = document.getElementById("command-palette-overlay");
    if (cp && !cp.classList.contains("hidden")) {
      import("./command-palette.js").then((m) => m.closeCommandPalette()).catch((e) => console.warn("Op:", e));
      e.preventDefault();
      return;
    }

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
