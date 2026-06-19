/* ═══════════════════════════════════
   DataForge — Billing / subscription view
   ═══════════════════════════════════ */

import { apiFetch } from "./api.js";
import { toast } from "./utils.js";

const TIER_LABELS = {
  free: "Free",
  pro: "Pro",
  team: "Team",
  starter: "Starter",
  enterprise: "Enterprise",
};

/** Map the operator's currently-rendered tier label to a checkout tier id.
 *
 * The PayPal dashboard recognises only ``starter`` / ``pro`` / ``enterprise``;
 * ``free`` and ``team`` are aliases we fold back to the next payable tier
 * or refuse to upgrade from.
 */
function _checkoutTierFor(currentTier) {
  const normalized = String(currentTier || "")
    .trim()
    .toLowerCase();
  if (normalized === "free" || normalized === "") return "starter";
  if (["starter", "pro", "enterprise"].includes(normalized)) return normalized;
  return null; // unknown tier — can't pick an upgrade target safely
}

function renderPlan(plan) {
  if (!plan) return;
  const setText = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.textContent = String(val);
  };
  setText("billing-kpi-tier", TIER_LABELS[plan.tier] || plan.tier || "—");
  setText("billing-kpi-jobs", plan.max_jobs ?? "—");
  setText("billing-kpi-scrapes", plan.max_scrapes ?? "—");
  setText("billing-kpi-teammates", plan.max_teammates ?? "—");

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

export async function refreshBilling() {
  try {
    const [planResp, subResp] = await Promise.all([apiFetch("/api/saas/plan"), apiFetch("/api/billing/subscriptions")]);

    if (planResp.ok) {
      const plan = await planResp.json();
      renderPlan(plan);
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
