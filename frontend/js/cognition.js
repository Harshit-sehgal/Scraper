/* ═══════════════════════════════════════════
   DataForge — Cognition State View
   ═══════════════════════════════════════════ */

import { esc, toast } from './utils.js';
import { API, apiFetch } from './api.js';

// ─── Refresh Cognition ───

export async function refreshCognition() {
    try {
        const res = await apiFetch(`${API}/api/system/topology`);
        if (!res.ok) throw new Error('Topology unavailable');
        const data = await res.json();

        const metrics = data.metrics || {};
        document.getElementById('kpi-pressure').textContent = (metrics.field_pressure || 0).toFixed(3);
        document.getElementById('kpi-integrity').textContent = (metrics.integrity_score || 0).toFixed(3);
        document.getElementById('kpi-energy').textContent = (metrics.global_energy || 0).toFixed(3);
        document.getElementById('kpi-exclusions').textContent = metrics.exclusion_count || 0;
        document.getElementById('kpi-basins').textContent = Array.isArray(data.field_regions) ? data.field_regions.length : 0;

        renderCommunities(data.global_communities);
        renderSchemaPatterns(data.schema_patterns);
        renderExclusions(data.learned_exclusions);
        renderRoleSimilarities(data.role_compatibility);
        renderBasins(data.field_regions);
    } catch (e) {
        toast(`Failed to load cognition state: ${e.message}`, 'error');
    }
}

// ─── Render Helpers ───

function renderCommunities(communities) {
    const el = document.getElementById('community-list');
    if (!communities || !communities.length) {
        el.innerHTML = '<div class="empty"><p>No stable communities identified</p></div>';
    } else {
        el.innerHTML = communities.map(c => `
            <div style="padding: 0.75rem; border-bottom: 1px solid var(--border);">
                <div style="display:flex; flex-wrap:wrap; gap:0.4rem;">
                    ${c.map(role => `<span class="mode-tag">${esc(role)}</span>`).join('')}
                </div>
            </div>
        `).join('');
    }
}

function renderSchemaPatterns(patterns) {
    const el = document.getElementById('schema-pattern-list');
    if (!patterns || !patterns.length) {
        el.innerHTML = '<div class="empty"><p>No recurring schemas learned yet</p></div>';
    } else {
        el.innerHTML = [...patterns].sort((a, b) => b.count - a.count).map(p => `
            <div style="padding: 0.75rem; border-bottom: 1px solid var(--border);">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div style="display:flex; flex-wrap:wrap; gap:0.4rem;">
                        ${p.roles.map(role => `<span class="mode-tag">${esc(role)}</span>`).join('')}
                    </div>
                    <span style="color:var(--text-muted); font-size:0.85rem;">Count: ${p.count}</span>
                </div>
            </div>
        `).join('');
    }
}

function renderExclusions(exclusions) {
    const el = document.getElementById('exclusion-list');
    if (!exclusions || !exclusions.length) {
        el.innerHTML = '<div class="empty"><p>No exclusions learned yet</p></div>';
    } else {
        el.innerHTML = [...exclusions].sort((a, b) => b.strength - a.strength).map(e => `
            <div style="display:flex; justify-content:space-between; padding: 0.5rem; border-bottom: 1px solid var(--border);">
                <span style="font-weight:600; color:var(--text-main);">${esc(e.roles.join(' ↔ '))}</span>
                <span style="color:var(--text-muted);">Strength: ${e.strength.toFixed(3)}</span>
            </div>
        `).join('');
    }
}

function renderRoleSimilarities(compats) {
    const el = document.getElementById('role-similarity-list');
    if (!compats || !compats.length) {
        el.innerHTML = '<div class="empty"><p>Manifold is cold</p></div>';
    } else {
        el.innerHTML = compats
            .filter(c => c.score > 0.7)
            .sort((a, b) => b.score - a.score)
            .map(c => `
                <div style="display:flex; justify-content:space-between; padding: 0.5rem; border-bottom: 1px solid var(--border);">
                    <span style="font-weight:600; color:var(--text-main);">${esc(c.role)} <span style="color:var(--text-muted); font-weight:400;">≈</span> ${esc(c.type)}</span>
                    <span style="color:var(--text-muted);">Score: ${c.score.toFixed(3)}</span>
                </div>
            `).join('');
    }
}

function renderBasins(basins) {
    const el = document.getElementById('basin-list');
    if (!basins || !basins.length) {
        el.innerHTML = '<div class="empty"><p>No active conflict basins</p></div>';
    } else {
        el.innerHTML = [...basins].sort((a, b) => b.instability - a.instability).map(b => `
            <div style="padding: 0.5rem; border-bottom: 1px solid var(--border);">
                <div style="font-weight:600; color:var(--text-main); margin-bottom:0.25rem;">Token: "${esc(b.token)}"</div>
                <div style="font-size:0.85rem; color:var(--text-muted); margin-bottom:0.25rem;">Clash: ${esc(b.competing_roles.join(', '))}</div>
                <div style="font-size:0.85rem; color:var(--text-muted); display:flex; gap:1rem;">
                    <span>Instability: ${b.instability.toFixed(3)}</span>
                    <span>Energy: ${b.local_energy.toFixed(3)}</span>
                </div>
            </div>
        `).join('');
    }
}
