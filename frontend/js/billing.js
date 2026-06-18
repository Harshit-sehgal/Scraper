/* ═══════════════════════════════════
   DataForge — Billing / subscription view
   ═══════════════════════════════════ */

import { apiFetch } from "./api.js";
import { toast } from "./utils.js";

const TIER_LABELS = {
  free: "Free",
  pro: "Pro",
  team: "Team",
  enterprise: "Enterprise",
};

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
  toast("Payment provider integration is not enabled. See docs/SAAS_MODEL.md.", "info");
}
