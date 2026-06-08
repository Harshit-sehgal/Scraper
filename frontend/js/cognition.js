/* ═══════════════════════════════════════════
   DataForge — Cognition State View
   ═══════════════════════════════════════════ */

import { esc, toast } from "./utils.js";
import { API, apiFetch } from "./api.js";

// ─── Refresh Cognition ───

export function renderCognitionSkeleton() {
  // Show skeleton loading state in the cognition view
  const kpiPressure = document.getElementById("kpi-pressure");
  if (kpiPressure)
    kpiPressure.innerHTML = '<span class="skeleton-bar" style="width:60%;height:14px;display:inline-block"></span>';
  const kpiIntegrity = document.getElementById("kpi-integrity");
  if (kpiIntegrity)
    kpiIntegrity.innerHTML = '<span class="skeleton-bar" style="width:50%;height:14px;display:inline-block"></span>';
  const kpiEnergy = document.getElementById("kpi-energy");
  if (kpiEnergy)
    kpiEnergy.innerHTML = '<span class="skeleton-bar" style="width:55%;height:14px;display:inline-block"></span>';
  const kpiExclusions = document.getElementById("kpi-exclusions");
  if (kpiExclusions)
    kpiExclusions.innerHTML = '<span class="skeleton-bar" style="width:40%;height:14px;display:inline-block"></span>';
  const kpiBasins = document.getElementById("kpi-basins");
  if (kpiBasins)
    kpiBasins.innerHTML = '<span class="skeleton-bar" style="width:45%;height:14px;display:inline-block"></span>';

  ["community-list", "schema-pattern-list", "exclusion-list", "role-similarity-list", "basin-list"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) {
      el.innerHTML = Array.from(
        { length: 4 },
        () => `
                <div style="padding:0.75rem;border-bottom:1px solid var(--line);">
                    <div class="skeleton-bar" style="width:${60 + Math.random() * 30}%;height:10px;margin:2px 0"></div>
                    <div class="skeleton-bar" style="width:${30 + Math.random() * 20}%;height:8px;margin:2px 0;opacity:0.6"></div>
                </div>`,
      ).join("");
    }
  });
}

export async function refreshCognition() {
  renderCognitionSkeleton();
  try {
    const res = await apiFetch(`${API}/api/system/topology`);
    // The topology endpoint sits behind the experimental-routes
    // gate. When ``DATAFORGE_ENABLE_EXPERIMENTAL_ROUTES`` is unset
    // the backend returns 403 with a ``X-DataForge-Feature-Flag``
    // header. Surface a friendly message instead of a generic
    // "Topology unavailable" toast that operators can't act on.
    if (res.status === 403) {
      _renderExperimentalGate("Cognition topology is part of the experimental surface and is disabled in this build.");
      return;
    }
    if (!res.ok) throw new Error(`Topology unavailable (${res.status})`);
    const data = await res.json();

    const metrics = data.metrics || {};
    const kpiPressure = document.getElementById("kpi-pressure");
    if (kpiPressure) kpiPressure.textContent = (metrics.field_pressure || 0).toFixed(3);
    const kpiIntegrity = document.getElementById("kpi-integrity");
    if (kpiIntegrity) kpiIntegrity.textContent = (metrics.integrity_score || 0).toFixed(3);
    const kpiEnergy = document.getElementById("kpi-energy");
    if (kpiEnergy) kpiEnergy.textContent = (metrics.global_energy || 0).toFixed(3);
    const kpiExclusions = document.getElementById("kpi-exclusions");
    if (kpiExclusions) kpiExclusions.textContent = metrics.exclusion_count || 0;
    const kpiBasins = document.getElementById("kpi-basins");
    if (kpiBasins) kpiBasins.textContent = Array.isArray(data.field_regions) ? data.field_regions.length : 0;

    renderCommunities(data.global_communities);
    renderSchemaPatterns(data.schema_patterns);
    renderExclusions(data.learned_exclusions);
    renderRoleSimilarities(data.role_compatibility);
    renderBasins(data.field_regions);
  } catch (e) {
    toast(`Failed to load cognition state: ${e.message}`, "error");
  }
}

function _renderExperimentalGate(message) {
  // Replace the skeleton/empty panels with a single in-place notice
  // so the operator knows the panel is unavailable by design and not
  // because of a transient error.
  const ids = ["community-list", "schema-pattern-list", "exclusion-list", "role-similarity-list", "basin-list"];
  for (const id of ids) {
    const el = document.getElementById(id);
    if (el) {
      el.innerHTML = `<div class="empty" style="padding:0.75rem;color:var(--text-muted);"><p>${esc(message)}</p></div>`;
    }
  }
  for (const id of ["kpi-pressure", "kpi-integrity", "kpi-energy", "kpi-exclusions", "kpi-basins"]) {
    const el = document.getElementById(id);
    if (el) {
      el.textContent = "—";
    }
  }
}

// ─── Render Helpers ───

export function renderCommunities(communities) {
  const el = document.getElementById("community-list");
  if (!el) return;
  if (!communities || !communities.length) {
    el.innerHTML = '<div class="empty"><p>No stable communities identified</p></div>';
  } else {
    el.innerHTML = communities
      .map(
        (c) => `
            <div style="padding: 0.75rem; border-bottom: 1px solid var(--border);">
                <div style="display:flex; flex-wrap:wrap; gap:0.4rem;">
                    ${(Array.isArray(c) ? c : []).map((role) => `<span class="mode-tag">${esc(role)}</span>`).join("")}
                </div>
            </div>
        `,
      )
      .join("");
  }
}

export function renderSchemaPatterns(patterns) {
  const el = document.getElementById("schema-pattern-list");
  if (!el) return;
  if (!patterns || !patterns.length) {
    el.innerHTML = '<div class="empty"><p>No recurring schemas learned yet</p></div>';
  } else {
    el.innerHTML = [...patterns]
      .sort((a, b) => (b.count ?? 0) - (a.count ?? 0))
      .map(
        (p) => `
            <div style="padding: 0.75rem; border-bottom: 1px solid var(--border);">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div style="display:flex; flex-wrap:wrap; gap:0.4rem;">
                        ${(p.roles || []).map((role) => `<span class="mode-tag">${esc(role)}</span>`).join("")}
                    </div>
                    <span style="color:var(--text-muted); font-size:0.85rem;">Count: ${p.count}</span>
                </div>
            </div>
        `,
      )
      .join("");
  }
}

export function renderExclusions(exclusions) {
  const el = document.getElementById("exclusion-list");
  if (!el) return;
  if (!exclusions || !exclusions.length) {
    el.innerHTML = '<div class="empty"><p>No exclusions learned yet</p></div>';
  } else {
    el.innerHTML = [...exclusions]
      .sort((a, b) => (b.strength ?? 0) - (a.strength ?? 0))
      .map(
        (e) => `
            <div style="display:flex; justify-content:space-between; padding: 0.5rem; border-bottom: 1px solid var(--border);">
                <span style="font-weight:600; color:var(--text-main);">${esc((e.roles || []).join(" ↔ "))}</span>
                <span style="color:var(--text-muted);">Strength: ${Number(e.strength || 0).toFixed(3)}</span>
            </div>
        `,
      )
      .join("");
  }
}

export function renderRoleSimilarities(compats) {
  const el = document.getElementById("role-similarity-list");
  if (!el) return;
  if (!compats || !compats.length) {
    el.innerHTML = '<div class="empty"><p>Manifold is cold</p></div>';
  } else {
    const filtered = compats.filter((c) => c.score > 0.7);
    if (!filtered.length) {
      el.innerHTML = '<div class="empty"><p>Manifold is cold</p></div>';
    } else {
      el.innerHTML = filtered
        .sort((a, b) => (b.score ?? 0) - (a.score ?? 0))
        .map(
          (c) => `
                <div style="display:flex; justify-content:space-between; padding: 0.5rem; border-bottom: 1px solid var(--border);">
                    <span style="font-weight:600; color:var(--text-main);">${esc(c.role)} <span style="color:var(--text-muted); font-weight:400;">≈</span> ${esc(c.type)}</span>
                    <span style="color:var(--text-muted);">Score: ${Number(c.score || 0).toFixed(3)}</span>
                </div>
            `,
        )
        .join("");
    }
  }
}

export function renderBasins(basins) {
  const el = document.getElementById("basin-list");
  if (!el) return;
  if (!basins || !basins.length) {
    el.innerHTML = '<div class="empty"><p>No active conflict basins</p></div>';
  } else {
    el.innerHTML = [...basins]
      .sort((a, b) => (b.instability ?? 0) - (a.instability ?? 0))
      .map(
        (b) => `
            <div style="padding: 0.5rem; border-bottom: 1px solid var(--border);">
                <div style="font-weight:600; color:var(--text-main); margin-bottom:0.25rem;">Token: "${esc(b.token)}"</div>
                <div style="font-size:0.85rem; color:var(--text-muted); margin-bottom:0.25rem;">Clash: ${esc((b.competing_roles || []).join(", "))}</div>
                <div style="font-size:0.85rem; color:var(--text-muted); display:flex; gap:1rem;">
                    <span>Instability: ${Number(b.instability || 0).toFixed(3)}</span>
                    <span>Energy: ${Number(b.local_energy || 0).toFixed(3)}</span>
                </div>
            </div>
        `,
      )
      .join("");
  }
}
