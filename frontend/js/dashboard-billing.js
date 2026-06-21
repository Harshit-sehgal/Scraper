/* ═══════════════════════════════════════════
   DataForge — Dashboard Billing Widget
   ═══════════════════════════════════════════
   Shows plan tier, usage bars, and upgrade CTA
   in the operations dashboard. */

import { apiFetch } from "./api.js";
import { esc } from "./utils.js";

const TIER_LABELS = {
  free: "Free",
  pro: "Pro",
  starter: "Starter",
  enterprise: "Enterprise",
};

/**
 * Fetch plan + usage data and render the billing widget.
 */
export async function refreshDashboardBilling() {
  const container = document.getElementById("dash-billing");
  if (!container) return;

  try {
    // Show loading state
    container.innerHTML = '<div class="dash-loading">Loading billing…</div>';

    const [planRes, jobsRes] = await Promise.all([
      apiFetch("/api/saas/plan").catch(() => null),
      apiFetch("/api/jobs?limit=1").catch(() => null),
    ]);

    const plan = planRes?.ok ? await planRes.json() : null;
    const jobsData = jobsRes?.ok ? await jobsRes.json() : null;
    const jobCount = Array.isArray(jobsData?.jobs) ? jobsData.jobs.length : 0;

    // Try to get actual scrape count from rate limit stats
    let scrapeCount = 0;
    try {
      const rateRes = await apiFetch("/api/system/rate-limit-stats");
      if (rateRes?.ok) {
        const rateData = await rateRes.json();
        scrapeCount = rateData.total_requests ?? rateData.api_requests ?? 0;
      }
    } catch {
      // Non-critical
    }

    renderBillingWidget(container, plan, jobCount, scrapeCount);
  } catch (err) {
    container.innerHTML = `<p class="subtle">Failed to load billing: ${esc(err.message)}</p>`;
  }
}

function renderBillingWidget(container, plan, jobCount, scrapeCount) {
  if (!plan) {
    container.innerHTML = `
      <div class="dash-card-body">
        <p class="subtle">Billing data unavailable.</p>
      </div>
    `;
    return;
  }

  const tier = TIER_LABELS[plan.tier] || plan.tier || "Free";
  const maxJobs = plan.max_jobs ?? 100;
  const maxScrapes = plan.max_scrapes ?? 1000;
  const maxTeammates = plan.max_teammates ?? 0;

  const jobPct = maxJobs > 0 ? Math.min(100, Math.round((jobCount / maxJobs) * 100)) : 0;
  const scrapePct = maxScrapes > 0 ? Math.min(100, Math.round((scrapeCount / maxScrapes) * 100)) : 0;

  const isNearLimit = jobPct >= 80 || scrapePct >= 80;

  container.innerHTML = `
    <div class="dash-card-body">
      <div class="billing-widget-tier">
        <span class="billing-widget-badge">${esc(tier)}</span>
      </div>

      <div class="billing-widget-usage">
        <div class="billing-widget-bar-row">
          <div class="billing-widget-bar-header">
            <span class="billing-widget-bar-label">Jobs</span>
            <span class="billing-widget-bar-val">${jobCount} / ${maxJobs}</span>
          </div>
          <div class="billing-widget-bar-track">
            <div class="billing-widget-bar-fill ${jobPct >= 90 ? "fill-critical" : jobPct >= 75 ? "fill-warning" : ""}"
              style="width: ${jobPct}%"></div>
          </div>
        </div>

        <div class="billing-widget-bar-row">
          <div class="billing-widget-bar-header">
            <span class="billing-widget-bar-label">Scrapes</span>
            <span class="billing-widget-bar-val">${scrapeCount} / ${maxScrapes}</span>
          </div>
          <div class="billing-widget-bar-track">
            <div class="billing-widget-bar-fill ${scrapePct >= 90 ? "fill-critical" : scrapePct >= 75 ? "fill-warning" : ""}"
              style="width: ${scrapePct}%"></div>
          </div>
        </div>

        <div class="billing-widget-bar-row">
          <div class="billing-widget-bar-header">
            <span class="billing-widget-bar-label">Teammates</span>
            <span class="billing-widget-bar-val">0 / ${maxTeammates || "∞"}</span>
          </div>
          <div class="billing-widget-bar-track">
            <div class="billing-widget-bar-fill" style="width: 0%"></div>
          </div>
        </div>
      </div>

      ${isNearLimit ? '<div class="billing-widget-note">Consider upgrading your plan</div>' : ""}

      <div class="billing-widget-actions">
        <button type="button" class="btn ghost small" data-action="switch-view" data-view="billing">
          View billing details
        </button>
      </div>
    </div>
  `;
}
