/* ═══════════════════════════════════
   DataForge — Billing / subscription view
   ═══════════════════════════════════ */

import { apiFetch } from "./api.js";
import { toast } from "./utils.js";

const TIER_LABELS = {
  free: "Free",
  pro: "Pro",
  starter: "Starter",
  enterprise: "Enterprise",
};

/** Plan tier metadata for the comparison table.
 *
 * Matches the PLAN_LIMITS dict in backend/app/billing/service.py.
 * Prices in USD/month. Enterprise uses -1 (unlimited).
 */
const PLANS = [
  {
    id: "free",
    name: "Free",
    price: "$0",
    period: "/month",
    description: "Get started with basic extraction needs",
    features: [
      { text: "10 jobs per month", included: true },
      { text: "1,000 pages per month", included: true },
      { text: "5 scheduled jobs", included: true },
      { text: "10,000 API requests / month", included: true },
      { text: "CSV / JSON / Excel export", included: true },
      { text: "Community support", included: true },
      { text: "Team collaboration", included: false },
      { text: "Priority support", included: false },
      { text: "Custom integrations", included: false },
    ],
    cta: "Current plan",
    featured: false,
  },
  {
    id: "starter",
    name: "Starter",
    price: "$29",
    period: "/month",
    description: "For growing teams with regular extraction needs",
    features: [
      { text: "100 jobs per month", included: true },
      { text: "10,000 pages per month", included: true },
      { text: "50 scheduled jobs", included: true },
      { text: "100,000 API requests / month", included: true },
      { text: "CSV / JSON / Excel export", included: true },
      { text: "Email support", included: true },
      { text: "Team collaboration (up to 3)", included: true },
      { text: "Priority support", included: false },
      { text: "Custom integrations", included: false },
    ],
    cta: "Subscribe",
    featured: true,
  },
  {
    id: "pro",
    name: "Pro",
    price: "$99",
    period: "/month",
    description: "For organizations running extraction at scale",
    features: [
      { text: "1,000 jobs per month", included: true },
      { text: "100,000 pages per month", included: true },
      { text: "500 scheduled jobs", included: true },
      { text: "1,000,000 API requests / month", included: true },
      { text: "CSV / JSON / Excel export", included: true },
      { text: "Priority support", included: true },
      { text: "Team collaboration (unlimited)", included: true },
      { text: "Custom integrations", included: false },
      { text: "Dedicated account manager", included: false },
    ],
    cta: "Subscribe",
    featured: false,
  },
  {
    id: "enterprise",
    name: "Enterprise",
    price: "$299",
    period: "/month",
    description: "For large-scale extraction with dedicated support",
    features: [
      { text: "Unlimited jobs", included: true },
      { text: "Unlimited pages", included: true },
      { text: "Unlimited scheduled jobs", included: true },
      { text: "Unlimited API requests", included: true },
      { text: "All export formats", included: true },
      { text: "Priority support (24/7)", included: true },
      { text: "Team collaboration (unlimited)", included: true },
      { text: "Custom integrations", included: true },
      { text: "Dedicated account manager", included: true },
    ],
    cta: "Contact sales",
    featured: false,
  },
];

/** Map the operator's currently-rendered tier label to a checkout tier id.
 *
 * The PayPal dashboard recognises only ``starter`` / ``pro`` / ``enterprise``.
 * Returning ``null`` for unknown / empty tiers lets the caller refuse
 * with a clear toast instead of silently picking a wrong target.
 */
function _checkoutTierFor(currentTier) {
  const normalized = String(currentTier || "")
    .trim()
    .toLowerCase();
  // Empty or clearly non-payable — ask the caller to refresh instead.
  if (normalized === "" || normalized === "—") return null;
  if (["starter", "pro", "enterprise"].includes(normalized)) return normalized;
  return null; // unknown tier — can't pick an upgrade target safely
}

function renderPlan(plan) {
  if (!plan) return;
  const setText = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.textContent = String(val);
  };
  const setMeter = (id, pct) => {
    const el = document.getElementById(id);
    if (!el) return;
    const clamped = Math.min(100, Math.max(0, pct));
    el.style.width = `${clamped}%`;
    el.classList.remove("fill-warning", "fill-critical");
    if (clamped > 95) el.classList.add("fill-critical");
    else if (clamped > 80) el.classList.add("fill-warning");
  };

  setText("billing-kpi-tier", TIER_LABELS[plan.tier] || plan.tier || "—");

  const maxJobs = plan.max_jobs ?? 0;
  const usedJobs = plan.used_jobs ?? 0;
  setText("billing-kpi-jobs", maxJobs > 0 ? `${usedJobs} / ${maxJobs}` : String(maxJobs || "—"));
  setMeter("billing-meter-jobs", maxJobs > 0 ? (usedJobs / maxJobs) * 100 : 0);

  const maxScrapes = plan.max_scrapes ?? 0;
  const usedScrapes = plan.used_scrapes ?? 0;
  setText("billing-kpi-scrapes", maxScrapes > 0 ? `${usedScrapes} / ${maxScrapes}` : String(maxScrapes || "—"));
  setMeter("billing-meter-scrapes", maxScrapes > 0 ? (usedScrapes / maxScrapes) * 100 : 0);

  const featuresEl = document.getElementById("billing-features");
  if (featuresEl) {
    const items = Array.isArray(plan.features) ? plan.features : [];
    if (items.length === 0) {
      featuresEl.innerHTML = '<li class="subtle">No features listed.</li>';
    } else {
      featuresEl.innerHTML = "";
      for (const f of items) {
        const li = document.createElement("li");
        li.textContent = f;
        featuresEl.appendChild(li);
      }
    }
  }
}

function renderSubscription(sub) {
  const el = document.getElementById("billing-subscription");
  if (!el) return;
  el.innerHTML = "";
  if (!sub) {
    el.innerHTML = '<p class="subtle">No active subscription. You are on the default free tier.</p>';
    return;
  }
  const dl = document.createElement("dl");
  dl.className = "billing-dl";
  for (const [k, v] of Object.entries(sub)) {
    const dt = document.createElement("dt");
    dt.textContent = k.replace(/_/g, " ");
    const dd = document.createElement("dd");
    dd.textContent = typeof v === "object" ? JSON.stringify(v) : String(v);
    dl.appendChild(dt);
    dl.appendChild(dd);
  }
  el.appendChild(dl);
}

/** Render the plan comparison table showing all available tiers. */
function renderPlanComparison(currentTierId) {
  const container = document.getElementById("billing-plan-comparison");
  if (!container) return;

  container.innerHTML = `<h2 class="billing-section-heading">Compare plans</h2>
    <div class="plan-comparison">
      ${PLANS.map((p) => {
        const isCurrent = p.id === currentTierId;
        const featuredClass = p.featured ? " featured" : "";
        return `<div class="plan-card${featuredClass}">
          <div class="plan-card-header">
            <span class="plan-card-name">${p.name}</span>
            <span class="plan-card-price">${p.price}</span>
            <span class="plan-card-price-period">${p.period}</span>
            <p class="subtle">${p.description}</p>
          </div>
          <div class="plan-card-features">
            ${p.features
              .map(
                (f) =>
                  `<span class="plan-card-feature${f.included ? "" : " disabled"}">
                <span class="icon">${f.included ? "✓" : "—"}</span>
                ${f.text}
              </span>`,
              )
              .join("")}
          </div>
          <div class="plan-card-action">
            ${
              isCurrent
                ? `<button type="button" class="btn secondary" disabled>Current plan</button>`
                : p.id === "enterprise"
                  ? `<a href="docs/SAAS_MODEL.md" class="btn secondary" target="_blank">Contact sales</a>`
                  : `<button type="button" class="btn primary" data-action="upgrade-to-tier" data-tier="${p.id}">${p.cta}</button>`
            }
          </div>
        </div>`;
      }).join("")}
    </div>`;

  // Wire upgrade-to-tier buttons (distinct from the existing upgrade-plan global handler)
  container.querySelectorAll('[data-action="upgrade-to-tier"]').forEach((btn) => {
    btn.addEventListener("click", () => {
      const tier = btn.dataset.tier;
      upgradeToTier(tier);
    });
  });
}

/**
 * Initiate checkout for a specific plan tier.
 * Unlike upgradePlan() which reads the current tier from the DOM,
 * this accepts the target tier directly.
 */
async function upgradeToTier(targetTier) {
  if (!targetTier || !["starter", "pro"].includes(targetTier)) {
    toast("Please select a valid plan tier to upgrade to.", "error");
    return;
  }

  const origin = window.location.origin || "";
  const returnUrl = `${origin}${window.location.pathname || "/"}?paypal_return=1&tier=${encodeURIComponent(targetTier)}`;
  const cancelUrl = `${origin}${window.location.pathname || "/"}?paypal_cancel=1`;

  let response;
  try {
    response = await apiFetch("/api/billing/checkout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        plan_tier: targetTier,
        return_url: returnUrl,
        cancel_url: cancelUrl,
      }),
    });
  } catch (err) {
    toast(`Checkout failed: ${err.message || err}`, "error");
    return;
  }

  if (!response || !response.ok) {
    toast(`Checkout failed (HTTP ${response.status}). See docs/SAAS_MODEL.md.`, "error");
    return;
  }

  let payload;
  try {
    payload = await response.json();
  } catch {
    toast("Checkout returned a malformed response.", "error");
    return;
  }

  const approvalUrl = payload?.approval_url;
  if (!approvalUrl) {
    toast("Checkout succeeded but no approval_url was returned.", "error");
    return;
  }

  window.location.href = approvalUrl;
}

export async function refreshBilling() {
  try {
    const [planResp, subResp] = await Promise.all([apiFetch("/api/saas/plan"), apiFetch("/api/billing/subscriptions")]);

    let currentTierId = "free";
    if (planResp.ok) {
      const plan = await planResp.json();
      renderPlan(plan);
      currentTierId = plan.tier || "free";
    } else {
      const setText = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.textContent = String(val);
      };
      setText("billing-kpi-tier", "—");
      toast(`Failed to load plan: HTTP ${planResp.status}`, "error");
    }

    if (subResp.ok) {
      const subs = await subResp.json();
      const items = Array.isArray(subs?.items) ? subs.items : Array.isArray(subs) ? subs : [];
      renderSubscription(items[0] || null);
    } else {
      // Subscriptions endpoint may require a project id; render placeholder.
      renderSubscription(null);
    }

    // Always render the plan comparison table
    renderPlanComparison(currentTierId);
  } catch (err) {
    toast(`Failed to load billing: ${err.message || err}`, "error");
  }
}

export async function upgradePlan() {
  // Read the currently-rendered tier so the operator's "upgrade" click
  // stirs PayPal toward a sensible target (Free → Starter unless they
  // are already mid-funnel on a labelled tier).
  const tierEl = document.getElementById("billing-kpi-tier");
  const currentTier = tierEl ? tierEl.textContent.trim() : "";
  const targetTier = _checkoutTierFor(currentTier);

  if (!targetTier) {
    toast("Unknown current tier — refresh the billing view before upgrading.", "error");
    return;
  }

  const origin = window.location.origin || "";
  const returnUrl = `${origin}${window.location.pathname || "/"}?paypal_return=1&tier=${encodeURIComponent(targetTier)}`;
  const cancelUrl = `${origin}${window.location.pathname || "/"}?paypal_cancel=1`;

  let response;
  try {
    response = await apiFetch("/api/billing/checkout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        plan_tier: targetTier,
        return_url: returnUrl,
        cancel_url: cancelUrl,
      }),
    });
  } catch (err) {
    toast(`Checkout failed: ${err.message || err}`, "error");
    return;
  }

  if (!response || !response.ok) {
    const detail = response ? `HTTP ${response.status}` : "no response";
    toast(`Checkout failed (${detail}). See docs/SAAS_MODEL.md.`, "error");
    return;
  }

  let payload;
  try {
    payload = await response.json();
  } catch {
    toast("Checkout returned a malformed response.", "error");
    return;
  }

  const approvalUrl = payload?.approval_url;
  if (!approvalUrl) {
    toast("Checkout succeeded but no approval_url was returned.", "error");
    return;
  }

  // PayPal sandbox/stub URLs are sandbox.example.com / example.com — let the
  // stub flow redirect the operator via window.location so the dev experience
  // mirrors production.
  window.location.href = approvalUrl;
}
