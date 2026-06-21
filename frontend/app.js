/* ═══════════════════════════════════════════
   Dataforge — Frontend App Entry Point (ES Module)
   ═══════════════════════════════════════════
   ═══════════════════════════════════════════ */

// ─── Init ───
import { hydrateIcons, icon, startIconObserver } from "./js/icons.js?v=4";
import {
  readUIState,
  updateJobsLastUpdatedLabel,
  initTheme,
  toggleTheme,
  showShortcuts,
  hideShortcuts,
  setEnginePolling,
  closeConfirm,
  executeConfirm,
  toast,
} from "./js/utils.js";
import { refreshSystemStatus, refreshJobs, refreshJobsManual, onJobsFilterChanged } from "./js/jobs.js";
import { onGlobalKeydown, switchView, getViewFromPath, currentView } from "./js/views.js";
import { refreshWorkflows, onWorkflowAction } from "./js/workflows.js";
import { checkAndRenderAupBanner, acceptAup, dismissAupBanner } from "./js/aup.js";
import { startHealthPill } from "./js/health-pill.js";
import {
  onResultsSliderInput,
  onResultsTableScroll,
  onResultsCellDoubleClick,
  renderFilteredResults,
  syncResultsScrollSlider,
} from "./js/results.js";
import {
  analyzeURL,
  toggleAllFields,
  applyAnalyzedFields,
  clearAnalysis,
  continueWithDirectScrape,
  createWorkflowDraftFromAnalysis,
  showAuthProfileEntryNotice,
} from "./js/analyzer.js";
import {
  addField,
  addFilter,
  suggestSchemaFromIntent,
  previewDiscovery,
  onFilterOpChange,
  submitJob,
} from "./js/form.js";
import { refreshCognition } from "./js/cognition.js";
import { refreshDashboard, switchOperatorMode } from "./js/dashboard.js";
import {
  restoreJob,
  hardDeleteJob,
  clearRecycleBin,
  handleRecycleSelectAll,
  handleRecycleSelectItem,
  batchRestore,
  batchHardDelete,
} from "./js/recycle.js";
import { cancelJob, deleteJob, clearTerminalJobs } from "./js/jobs.js";
import {
  viewResults,
  recleanCurrentJob,
  exportCSV,
  exportJSON,
  exportExcel,
  copySampleRow,
  goToFirstPage,
  goToPrevPage,
  goToNextPage,
  goToLastPage,
  goToPage,
} from "./js/results.js";
import { showApiKeyPrompt, showAdminKeyPrompt, closeKeyModal, saveKeyFromModal, checkSession } from "./js/api.js";
import { setMode } from "./js/views.js";
import { initAuthProfiles } from "./js/auth-profiles.js";
import { initScheduledMonitoring, refreshScheduledJobs, deleteScheduledJob } from "./js/scheduled-monitoring.js";
import { refreshBilling, upgradePlan } from "./js/billing.js";
import { findDuplicates, removeDuplicates, clearDuplicateState } from "./js/duplicate-detection.js";
import { analyzeCleaning, applyCleaningAction, clearCleaningState } from "./js/data-cleaning.js";
import { showDataProfile, clearProfileState } from "./js/data-profile.js";
import { refreshAudit } from "./js/audit.js";
import { refreshRetention, deleteMyData } from "./js/retention.js";

function onDocumentClick(e) {
  const btn = e.target.closest("[data-action]");
  if (!btn) return;

  const action = btn.getAttribute("data-action");
  const id = btn.getAttribute("data-id") || "";
  const mode = btn.getAttribute("data-mode") || "";
  const view = btn.getAttribute("data-view") || "";

  switch (action) {
    case "view-results":
      if (id) viewResults(id);
      break;
    case "cancel-job":
      if (id) cancelJob(id);
      break;
    case "delete-job":
      if (id) deleteJob(id);
      break;
    case "restore-job":
      if (id) restoreJob(id);
      break;
    case "hard-delete-job":
      if (id) hardDeleteJob(id);
      break;
    case "remove-field":
      btn.closest(".field-row")?.remove();
      break;
    case "remove-filter":
      btn.closest(".filter-row")?.remove();
      break;
    case "toast-info": {
      const msg = btn.getAttribute("data-message");
      if (msg) toast(msg, "info");
      break;
    }
    case "save-apikey":
      saveKeyFromModal();
      break;
    case "close-apikey":
      closeKeyModal();
      break;
    case "show-api-key":
      switchView("api-keys");
      break;
    case "show-admin-key":
      switchView("api-keys");
      break;
    case "save-api-key":
      import("./js/api-keys-page.js").then((m) => m.saveApiKeyFromPage()).catch(() => {});
      break;
    case "clear-api-key":
      import("./js/api-keys-page.js").then((m) => m.clearApiKeyFromPage()).catch(() => {});
      break;
    case "toggle-api-key-vis":
      import("./js/api-keys-page.js").then((m) => m.toggleApiKeyVisibility()).catch(() => {});
      break;
    case "save-admin-key":
      import("./js/api-keys-page.js").then((m) => m.saveAdminKeyFromPage()).catch(() => {});
      break;
    case "clear-admin-key":
      import("./js/api-keys-page.js").then((m) => m.clearAdminKeyFromPage()).catch(() => {});
      break;
    case "toggle-admin-key-vis":
      import("./js/api-keys-page.js").then((m) => m.toggleAdminKeyVisibility()).catch(() => {});
      break;
    case "refresh-api-keys":
      import("./js/api-keys-page.js").then((m) => m.refreshApiKeysPage()).catch(() => {});
      break;
    case "logout-session":
      import("./js/api-keys-page.js").then((m) => m.logoutFromPage()).catch(() => {});
      break;
    case "set-theme-mode":
      import("./js/settings-page.js").then((m) => m.setThemeMode(mode)).catch(() => {});
      break;
    case "open-command-palette":
      import("./js/command-palette.js").then((m) => m.openCommandPalette()).catch(() => {});
      break;
    case "refresh-scheduled":
      refreshScheduledJobs();
      break;
    case "delete-scheduled-job":
      if (id) deleteScheduledJob(id);
      break;
    case "switch-view":
      if (view) switchView(view);
      break;
    case "toggle-sidebar": {
      const layout = document.getElementById("app-layout");
      if (layout) {
        const isClosed = layout.dataset.sidebar === "closed";
        layout.dataset.sidebar = isClosed ? "open" : "closed";
      }
      break;
    }
    case "clear-terminal-jobs":
      clearTerminalJobs();
      break;
    case "refresh-jobs":
      refreshJobsManual();
      break;
    case "clear-recycle-bin":
      clearRecycleBin();
      break;
    case "recycle-select-all":
      handleRecycleSelectAll(btn.checked);
      break;
    case "recycle-batch-restore":
      batchRestore();
      break;
    case "recycle-batch-delete":
      batchHardDelete();
      break;
    case "refresh-dashboard":
      refreshDashboard();
      break;
    case "refresh-auth-profiles":
      import("./js/auth-profiles.js").then((m) => m.refreshAuthProfiles()).catch(() => {});
      break;
    case "switch-operator-mode":
      if (mode) switchOperatorMode(mode);
      break;
    case "analyze-url":
      analyzeURL();
      break;
    case "refresh-workflows":
      refreshWorkflows();
      break;
    case "run-workflow":
    case "delete-workflow":
      onWorkflowAction(action, id);
      break;
    case "aup-accept": {
      const v = btn.getAttribute("data-version") || "";
      acceptAup(v);
      break;
    }
    case "aup-dismiss":
      dismissAupBanner();
      break;
    case "refresh-billing":
      refreshBilling();
      break;
    case "refresh-audit":
      refreshAudit();
      break;
    case "refresh-retention":
      refreshRetention();
      break;
    case "upgrade-plan":
      upgradePlan();
      break;
    case "delete-my-data":
      deleteMyData();
      break;
    case "send-email-verification":
      import("./js/email-verification.js").then((m) => m.sendEmailVerification()).catch(() => {});
      break;
    case "verify-email-token":
      import("./js/email-verification.js").then((m) => m.verifyEmailToken()).catch(() => {});
      break;
    case "request-password-reset":
      import("./js/password-reset.js").then((m) => m.requestPasswordReset()).catch(() => {});
      break;
    case "confirm-password-reset":
      import("./js/password-reset.js").then((m) => m.confirmPasswordReset()).catch(() => {});
      break;
    case "create-invitation":
      import("./js/invitations.js").then((m) => m.createInvitation()).catch(() => {});
      break;
    case "accept-invitation": {
      const invId = id || btn.getAttribute("data-id") || "";
      if (invId) import("./js/invitations.js").then((m) => m.respondToInvitation(invId, true)).catch(() => {});
      break;
    }
    case "decline-invitation": {
      const invId = id || btn.getAttribute("data-id") || "";
      if (invId) import("./js/invitations.js").then((m) => m.respondToInvitation(invId, false)).catch(() => {});
      break;
    }
    case "refresh-invitations":
      import("./js/invitations.js").then((m) => m.refreshInvitations()).catch(() => {});
      break;
    case "toggle-all-fields":
      toggleAllFields(btn.getAttribute("data-select") === "true");
      break;
    case "apply-fields":
      applyAnalyzedFields();
      break;
    case "clear-analysis":
      clearAnalysis();
      break;
    case "url-direct-scrape":
      continueWithDirectScrape();
      break;
    case "url-create-workflow-draft":
      createWorkflowDraftFromAnalysis();
      break;
    case "url-auth-profile":
      showAuthProfileEntryNotice();
      break;
    case "set-mode":
      if (mode) setMode(mode);
      break;
    case "suggest-schema":
      suggestSchemaFromIntent();
      break;
    case "preview-discovery":
      previewDiscovery();
      break;
    case "add-field":
      addField();
      break;
    case "add-filter":
      addFilter();
      break;
    case "reclean-job":
      recleanCurrentJob();
      break;
    case "export-csv":
      exportCSV();
      break;
    case "export-json":
      exportJSON();
      break;
    case "export-excel":
      exportExcel();
      break;
    case "copy-sample-row":
      copySampleRow();
      break;
    case "go-to-first-page":
      goToFirstPage();
      break;
    case "go-to-prev-page":
      goToPrevPage();
      break;
    case "go-to-next-page":
      goToNextPage();
      break;
    case "go-to-last-page":
      goToLastPage();
      break;
    case "find-duplicates":
      findDuplicates();
      break;
    case "remove-duplicates":
      removeDuplicates();
      break;
    case "analyze-cleaning":
      analyzeCleaning();
      break;
    case "apply-cleaning":
      applyCleaningAction();
      break;
    case "show-data-profile":
      showDataProfile();
      break;
    case "hide-profile-panel":
      clearProfileState();
      {
        const panel = document.getElementById("profile-panel");
        if (panel) panel.classList.add("hidden");
      }
      break;
    case "hide-cleaning-panel":
      clearCleaningState();
      {
        const panel = document.getElementById("cleaning-panel");
        if (panel) panel.classList.add("hidden");
      }
      break;
    case "hide-duplicate-panel":
      clearDuplicateState();
      {
        const panel = document.getElementById("dup-panel");
        if (panel) panel.classList.add("hidden");
      }
      break;
    case "go-to-page": {
      const page = btn.getAttribute("data-page");
      if (page) goToPage(page);
      break;
    }
    case "toggle-theme":
      toggleTheme();
      break;
    case "show-shortcuts":
      showShortcuts();
      break;
    case "close-shortcuts":
      hideShortcuts();
      break;
    case "close-confirm":
      closeConfirm();
      break;
    case "confirm-action":
      executeConfirm();
      break;
    case "copy-job-id":
      if (id)
        navigator.clipboard
          ?.writeText?.(id)
          ?.then?.(() => {
            btn.innerHTML = icon("check", 14);
            btn.classList.add("copied");
            setTimeout(() => {
              btn.innerHTML = icon("copy", 14);
              btn.classList.remove("copied");
            }, 2000);
          })
          ?.catch?.(() => {});
      break;
    case "refresh-cognition":
      refreshCognition();
      break;
    case "toggle-field-item": {
      // If the user clicked the checkbox itself, the change handler
      // below will already have toggled the `selected` class. Skip
      // here to avoid double-toggling (which would silently undo the
      // user's click).
      if (e.target.matches(".analyze-field-checkbox")) {
        break;
      }
      const checkbox = btn.querySelector(".analyze-field-checkbox");
      if (checkbox) {
        checkbox.checked = !checkbox.checked;
        btn.classList.toggle("selected", checkbox.checked);
      }
      break;
    }
  }
}

function onDocumentChange(e) {
  const sel = e.target.closest(".ff-op");
  if (sel) {
    onFilterOpChange(sel);
  }

  const checkbox = e.target.closest(".analyze-field-checkbox");
  if (checkbox) {
    const item = checkbox.closest(".analyze-field-item");
    if (item) item.classList.toggle("selected", checkbox.checked);
  }

  // Recycle bin individual item checkbox
  const recycleCheck = e.target.closest(".recycle-check-item");
  if (recycleCheck) {
    const id = recycleCheck.getAttribute("data-id");
    if (id) handleRecycleSelectItem(id, recycleCheck.checked);
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  // Attach delegated handlers before the first network await so early
  // user clicks on visible controls are not dropped during startup.
  document.addEventListener("click", onDocumentClick);
  document.addEventListener("change", onDocumentChange);

  // Hydrate [data-icon] placeholders with Phosphor SVG icons
  hydrateIcons();
  // Watch for future innerHTML rewrites so view-local mutations
  // (renderJobs, addField, addFilter, etc.) keep their icons rendered
  // without needing per-render explicit hydrateIcons() calls.
  startIconObserver();

  // G2: Try session auth first — if the browser already has a valid
  // session cookie, no API key prompt is needed.
  await checkSession();

  // Start the topbar health pill — periodic probe of /api/health + /api/ready.
  startHealthPill();

  // Fetch experimental feature flag from the public root endpoint
  // and reveal experimental UI elements when enabled.
  fetch("/")
    .then((r) => r.json())
    .then((data) => {
      if (data.experimental_enabled) {
        document.body.dataset.experimental = "true";
        // F-003: the cognition-view guards in views.js compare
        // ``window.DATAFORGE_EXPERIMENTAL !== true``; without setting it
        // here, the Cognition tab visibly appears (via the dataset class)
        // but is functionally unreachable — clicking it redirects to Jobs.
        window.DATAFORGE_EXPERIMENTAL = true;
        document.querySelectorAll('[data-experimental="true"]').forEach((el) => {
          el.classList.add("visible");
        });
      }
      // Once we know the active AUP version, surface the
      // acceptance banner if needed. The check is silent on
      // 404/401 (no auth, no banner) so it never nags anonymous
      // visitors.
      if (data.aup_version) {
        checkAndRenderAupBanner(data.aup_version);
      }
    })
    .catch(() => {});

  const uiState = readUIState();

  // Restore search/status filters
  const jobsSearch = document.getElementById("jobs-search");
  if (jobsSearch && typeof uiState.jobsSearch === "string") {
    jobsSearch.value = uiState.jobsSearch;
  }
  if (jobsSearch) jobsSearch.addEventListener("input", onJobsFilterChanged);

  const jobsStatus = document.getElementById("jobs-status-filter");
  if (jobsStatus && typeof uiState.jobsStatus === "string") {
    jobsStatus.value = uiState.jobsStatus;
  }
  if (jobsStatus) jobsStatus.addEventListener("change", onJobsFilterChanged);

  const resultSearch = document.getElementById("inp-result-search");
  if (resultSearch) resultSearch.addEventListener("input", renderFilteredResults);

  const resultsSlider = document.getElementById("results-scroll-slider");
  if (resultsSlider) resultsSlider.addEventListener("input", onResultsSliderInput);

  const tableWrap = document.querySelector("#view-results .table-wrap");
  if (tableWrap) tableWrap.addEventListener("scroll", onResultsTableScroll);

  const resultBody = document.getElementById("res-tbody");
  if (resultBody) resultBody.addEventListener("dblclick", onResultsCellDoubleClick);

  // URL Analyzer: Enter key triggers analysis. The handler also
  // checks the analyze button's disabled state so a fast double
  // press of Enter — which would otherwise bypass the button
  // debounce and fire two parallel API calls — is ignored while
  // the first request is in flight.
  const analyzeUrlInput = document.getElementById("inp-analyze-url");
  if (analyzeUrlInput) {
    analyzeUrlInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        const analyzeBtn = document.getElementById("btn-analyze-url");
        if (analyzeBtn && analyzeBtn.disabled) return;
        analyzeURL();
      }
    });
  }

  // ── API Key Modal: Enter saves, Escape cancels ──
  const apikeyForm = document.getElementById("apikey-form");
  if (apikeyForm) {
    apikeyForm.addEventListener("submit", (e) => {
      e.preventDefault();
      saveKeyFromModal();
    });
  }
  const apikeyInput = document.getElementById("apikey-input");
  if (apikeyInput) {
    apikeyInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        saveKeyFromModal();
      }
      if (e.key === "Escape") {
        e.preventDefault();
        closeKeyModal();
      }
    });
  }

  // ── API Key Toggle Visibility ──
  const apikeyToggle = document.getElementById("apikey-toggle-vis");
  if (apikeyToggle) {
    apikeyToggle.addEventListener("change", () => {
      const input = document.getElementById("apikey-input");
      if (input) input.type = apikeyToggle.checked ? "text" : "password";
    });
  }

  // ── Global keyboard ──
  document.addEventListener("keydown", onGlobalKeydown);

  // ── Window focus / visibility ──
  // Tab-switching in modern browsers fires a flurry of
  // ``visibilitychange`` and ``focus`` events when the user
  // hovers over the tab strip or alt-tabs. Each of those events
  // would otherwise kick off three API calls, so we coalesce
  // them with a one-shot timer. The latest event wins; earlier
  // ones are dropped before they reach the network.
  let _focusRefreshTimer = null;
  const _scheduleFocusRefresh = () => {
    if (_focusRefreshTimer) return;
    _focusRefreshTimer = setTimeout(() => {
      _focusRefreshTimer = null;
      refreshSystemStatus();
      refreshJobs();
      updateJobsLastUpdatedLabel();
    }, 250);
  };
  window.addEventListener("focus", _scheduleFocusRefresh);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) {
      _scheduleFocusRefresh();
    }
  });

  // ── Resize ──
  // The horizontal scroll-snap slider needs to recompute its range
  // when the viewport changes width. ResizeObserver is a no-op for
  // window, so we hook the event directly and call the exported
  // ``syncResultsScrollSlider`` from results.js. We do not dispatch a
  // synthetic ``scroll`` event on the table wrap — that would mix input
  // and resize handling and could fire onResultsTableScroll() with a
  // stale state.
  window.addEventListener("resize", () => syncResultsScrollSlider());

  // ── Init theme ──
  initTheme();

  // ── Topbar scroll shadow ──
  const topbar = document.querySelector(".topbar");
  if (topbar) {
    const onTopbarScroll = () => {
      topbar.classList.toggle("scrolled", window.scrollY > 4);
    };
    window.addEventListener("scroll", onTopbarScroll, { passive: true });
    onTopbarScroll();
  }

  // ── Init auth profiles module ──
  initAuthProfiles();

  // ── Init scheduled monitoring module ──
  initScheduledMonitoring();

  // ── Initial view ──
  // URL path takes precedence over localStorage state
  let initialView = getViewFromPath(window.location.pathname);
  // Fall back to saved state if URL is at root and we have a saved view
  if (initialView === "jobs" && window.location.pathname === "/" && uiState.view) {
    initialView = uiState.view;
  }
  // H2: Guard initial view restoration for cognition
  if (initialView === "cognition" && window.DATAFORGE_EXPERIMENTAL !== true) {
    initialView = "jobs";
  }
  switchView(initialView);

  // ── Polling Intervals (refactored to use setInterval with cleanup) ──
  class JobStatusPoller {
    constructor(callback, interval, name = "poller") {
      this.callback = callback;
      this.interval = interval;
      this.name = name;
      this.timer = null;
      this.isRunning = false;
    }

    async _tick() {
      if (document.hidden) return; // Skip if tab is not visible to save resources
      this.isRunning = true;
      setEnginePolling(true);
      try {
        await this.callback();
      } catch (e) {
        console.warn(`"Polling error in ${this.name}:"`, e);
      } finally {
        setEnginePolling(false);
        this.isRunning = false;
      }
    }

    start() {
      if (this.timer) return;
      this.timer = setInterval(() => this._tick(), this.interval);
    }

    stop() {
      if (this.timer) {
        clearInterval(this.timer);
        this.timer = null;
      }
    }
  }

  const refreshInterval =
    typeof window.DATAFORGE_REFRESH_INTERVAL === "number" ? window.DATAFORGE_REFRESH_INTERVAL : 10000;
  const statusInterval =
    typeof window.DATAFORGE_STATUS_INTERVAL === "number" ? window.DATAFORGE_STATUS_INTERVAL : 10000;

  // Initialize pollers
  const jobsPoller = new JobStatusPoller(refreshJobs, refreshInterval, "jobs");
  const statusPoller = new JobStatusPoller(refreshSystemStatus, statusInterval, "status");

  jobsPoller.start();
  statusPoller.start();

  // Cleanup on page unload
  window.addEventListener("beforeunload", () => {
    jobsPoller.stop();
    statusPoller.stop();
  });

  // Engine connection check
  window.addEventListener("online", () => setEnginePolling(true));
  window.addEventListener("offline", () => setEnginePolling(false));

  // ── Job form submit ──
  const jobForm = document.getElementById("job-form");
  if (jobForm) {
    jobForm.addEventListener("submit", submitJob);
  }

  // Expose currentView for dashboard polling via a getter
  window.__DATAFORGE_VIEW = {};
  Object.defineProperty(window.__DATAFORGE_VIEW, "currentView", {
    get: () => currentView,
    enumerable: true,
  });
});
