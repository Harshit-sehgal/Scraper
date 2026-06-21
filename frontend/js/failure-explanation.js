/* ═══════════════════════════════════════════
   DataForge — Failure Explanation Assistant
   ═══════════════════════════════════════════
   Maps job failure signals to user-friendly messages
   and recommended actions, rendered inline in the UI.
   ═══════════════════════════════════════════ */

import { esc, toast } from "./utils.js";

// ─── Failure Type Taxonomy ───

const FAILURE_MAP = {
  login_required: {
    icon: "🔐",
    title: "Login Required",
    message: "This page requires a login session.",
    detail: "The target page returned a login form or redirect to an authentication endpoint.",
    action:
      "Create an Auth Profile: go to Auth Profiles, click 'Create', enter the domain, and complete the login flow.",
  },
  session_expired: {
    icon: "⏰",
    title: "Session Expired",
    message: "Your session for this website has expired.",
    detail: "The stored session cookies are no longer valid. The site returned a session-expired indicator.",
    action: "Go to Auth Profiles, find the expired profile, and click 'Reconnect' to refresh the session.",
  },
  session_url: {
    icon: "🔗",
    title: "Temporary Session URL",
    message: "This URL uses a temporary session that may expire.",
    detail: "The URL contains session-bound parameters that may expire quickly.",
    action: "Use Workflow Replay to create a reliable scraping workflow that navigates from the main page.",
  },
  selector_not_found: {
    icon: "🎯",
    title: "Page Structure Changed",
    message: "The page structure has changed and expected data could not be found.",
    detail: "Configured CSS selectors or heuristics did not match any elements on the page.",
    action: "Use the URL Analyzer to re-detect fields, or manually update the selector mapping.",
  },
  blocked: {
    icon: "🛡️",
    title: "Access Blocked",
    message: "The website blocked automated access.",
    detail: "Anti-bot signals detected: CAPTCHA, rate-limit response, or bot challenge page.",
    action: "Pause and retry later, reduce request frequency, or contact the site owner for permission.",
  },
  timeout: {
    icon: "⏳",
    title: "Page Timed Out",
    message: "The page took too long to load.",
    detail: "The request exceeded the configured timeout threshold.",
    action: "Increase the wait timeout in job settings, or reduce the extraction scope (fewer pages).",
  },
  network_error: {
    icon: "🌐",
    title: "Network Error",
    message: "Could not reach the website.",
    detail: "DNS resolution failed, connection refused, or HTTP error.",
    action: "Check that the URL is correct and the website is accessible. Try again later.",
  },
  no_records: {
    icon: "📭",
    title: "No Data Found",
    message: "No data records were found on this page.",
    detail: "The extraction ran successfully but produced zero records.",
    action: "Verify the URL and selectors. The page may be empty or data may be loaded dynamically.",
  },
  quota_exceeded: {
    icon: "📊",
    title: "Usage Limit Reached",
    message: "You have reached your usage limit for this plan.",
    detail: "Quota check returned over-limit for the current billing period.",
    action: "Upgrade your plan or wait until the next billing period.",
  },
  domain_blocked: {
    icon: "🚫",
    title: "Domain Not Allowed",
    message: "This website is not allowed for scraping.",
    detail: "The URL safety check rejected the domain as unsafe or against policy.",
    action: "Review the Acceptable Use Policy. If you believe this is an error, contact support.",
  },
  browser_crash: {
    icon: "🤖",
    title: "Browser Crashed",
    message: "The browser engine crashed during extraction.",
    detail: "The Playwright browser or context closed unexpectedly.",
    action: "Reduce browser concurrency or retry. If the issue persists, check system resources.",
  },
  partial_extraction: {
    icon: "📋",
    title: "Partial Results",
    message: "Only some fields were populated.",
    detail: "Not all expected data fields could be extracted.",
    action: "Try re-running with the URL Analyzer to detect additional fields.",
  },
  low_quality: {
    icon: "⚠️",
    title: "Low Quality Data",
    message: "Extracted data scored below quality thresholds.",
    detail: "Records were extracted but all scored below the minimum quality score.",
    action: "Lower the quality threshold in Advanced Options, or try a different extraction method.",
  },
  unknown: {
    icon: "❌",
    title: "Extraction Error",
    message: "An unexpected error occurred during extraction.",
    detail: "An unhandled exception was raised during the extraction pipeline.",
    action: "Try again. If the issue persists, check the logs or contact support.",
  },
};

// ─── Classify a Job's Failure ───

export function classifyJobFailure(job) {
  if (!job) return null;

  const status = (job.status || "").toLowerCase();
  const errorMsg = (job.error || "").toLowerCase();
  const warnings = Array.isArray(job.warnings) ? job.warnings : [];

  // Check for specific error patterns in the error message
  // Session expiry must be checked before login_required because an expired-session
  // error often also mentions "login" (e.g. "Session expired, please login again").
  if (errorMsg.includes("session") && (errorMsg.includes("expired") || errorMsg.includes("invalid"))) {
    return "session_expired";
  }
  if (errorMsg.includes("login") || errorMsg.includes("sign in") || errorMsg.includes("authenticate")) {
    return "login_required";
  }
  if (
    errorMsg.includes("captcha") ||
    errorMsg.includes("challenge") ||
    errorMsg.includes("blocked") ||
    errorMsg.includes("403")
  ) {
    return "blocked";
  }
  if (errorMsg.includes("timeout") || errorMsg.includes("timed out")) {
    return "timeout";
  }
  if (
    errorMsg.includes("dns") ||
    errorMsg.includes("connection") ||
    errorMsg.includes("refused") ||
    errorMsg.includes("econn")
  ) {
    return "network_error";
  }
  if (errorMsg.includes("quota") || errorMsg.includes("rate limit") || errorMsg.includes("429")) {
    return "quota_exceeded";
  }
  if (errorMsg.includes("selector") || errorMsg.includes("no element") || errorMsg.includes("not found")) {
    return "selector_not_found";
  }
  if (errorMsg.includes("browser") || errorMsg.includes("crash") || errorMsg.includes("context closed")) {
    return "browser_crash";
  }
  if (errorMsg.includes("domain") || errorMsg.includes("not allowed") || errorMsg.includes("unsafe")) {
    return "domain_blocked";
  }

  // Check warnings for additional context
  for (const w of warnings) {
    const wMsg = (w.message || w || "").toLowerCase();
    if (wMsg.includes("session") && wMsg.includes("param")) return "session_url";
    if (wMsg.includes("partial") || wMsg.includes("missing field")) return "partial_extraction";
    if (wMsg.includes("quality") || wMsg.includes("low score")) return "low_quality";
  }

  // Fall back to status-based classification
  if (status === "empty_result") return "no_records";
  if (status === "degraded") return "partial_extraction";
  if (status === "failed" || status === "error") return "unknown";

  return null;
}

// ─── Get Explanation for a Failure Type ───

export function getFailureExplanation(failureType) {
  return FAILURE_MAP[failureType] || FAILURE_MAP.unknown;
}

// ─── Render a Failure Badge for the Jobs List ───

export function renderFailureBadge(job) {
  const failureType = classifyJobFailure(job);
  if (!failureType) return "";

  const explanation = getFailureExplanation(failureType);

  return `
    <div class="failure-badge" data-failure-type="${failureType}" title="${esc(explanation.detail)}">
      <span class="failure-badge-icon">${explanation.icon}</span>
      <span class="failure-badge-text">${esc(explanation.title)}</span>
    </div>
  `;
}

// ─── Render a Full Failure Explanation Panel ───

export function renderFailurePanel(job) {
  const failureType = classifyJobFailure(job);
  if (!failureType) return "";

  const explanation = getFailureExplanation(failureType);
  const errorMsg = job.error || "";
  const hasDetail = errorMsg.length > 0;

  return `
    <div class="failure-panel" data-failure-type="${failureType}">
      <div class="failure-panel-header">
        <span class="failure-panel-icon">${explanation.icon}</span>
        <div class="failure-panel-title-group">
          <h3 class="failure-panel-title">${esc(explanation.title)}</h3>
          <p class="failure-panel-message">${esc(explanation.message)}</p>
        </div>
      </div>
      <div class="failure-panel-body">
        <div class="failure-panel-section">
          <span class="failure-panel-section-label">What happened</span>
          <p class="failure-panel-text">${esc(explanation.detail)}</p>
        </div>
        ${
          hasDetail
            ? `
          <details class="failure-panel-details">
            <summary>Technical details</summary>
            <pre class="failure-panel-error">${esc(errorMsg)}</pre>
          </details>
        `
            : ""
        }
        <div class="failure-panel-section">
          <span class="failure-panel-section-label">Recommended action</span>
          <p class="failure-panel-text failure-panel-action">${esc(explanation.action)}</p>
        </div>
      </div>
    </div>
  `;
}

// ─── Render a Compact Tooltip for Inline Display (used in job rows) ───

export function renderFailureTooltip(job) {
  const failureType = classifyJobFailure(job);
  if (!failureType) return "";

  const explanation = getFailureExplanation(failureType);

  return `
    <div class="failure-tooltip" role="tooltip">
      <div class="failure-tooltip-header">
        <span>${explanation.icon}</span>
        <strong>${esc(explanation.title)}</strong>
      </div>
      <p class="failure-tooltip-msg">${esc(explanation.message)}</p>
      <p class="failure-tooltip-action">${esc(explanation.action)}</p>
    </div>
  `;
}

// ─── Wire Up Interactive Failure Badges ───

export function initFailureBadges() {
  document.querySelectorAll(".failure-badge[data-failure-type]").forEach((badge) => {
    // Click to show a toast with the recommended action
    badge.addEventListener("click", (e) => {
      e.stopPropagation();
      const failureType = badge.dataset.failureType;
      const explanation = getFailureExplanation(failureType);
      toast(`${explanation.icon} ${explanation.message} — ${explanation.action}`, "info", 5000);
    });
  });
}

// ─── Auto-detect from job after render ───

export function attachFailureExplanationToJobRow(jobRow, job) {
  if (!jobRow || !job) return;

  const failureType = classifyJobFailure(job);
  if (!failureType) return;

  const explanation = getFailureExplanation(failureType);

  // Add a failure indicator to the row
  jobRow.classList.add(`failure-${failureType}`);

  // Show the explanation as a tooltip on hover of the status badge
  const statusBadge = jobRow.querySelector(".badge.failed");

  if (statusBadge) {
    const tooltipEl = document.createElement("div");
    tooltipEl.className = "failure-inline-tooltip";
    tooltipEl.innerHTML = `
      <div class="failure-inline-tooltip-content">
        <div class="failure-inline-tooltip-header">
          <span>${explanation.icon}</span>
          <strong>${esc(explanation.title)}</strong>
        </div>
        <p>${esc(explanation.message)}</p>
        <p class="failure-inline-tooltip-action">${esc(explanation.action)}</p>
      </div>
    `;
    statusBadge.appendChild(tooltipEl);
  }
}
