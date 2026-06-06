/**
 * Semantic Reliability Dashboard JS
 * Polling topology visualization and drift monitoring.
 */

// ─── API key management (shared with main dashboard) ───────────────────
// SECURITY: API key is held in memory only — never in sessionStorage /
// localStorage. Page reload clears the key; the user re-enters it.
let _dashboardApiKey = "";

function getDashboardApiKey() {
    return _dashboardApiKey;
}

function setDashboardApiKey(key) {
    _dashboardApiKey = (key || "").trim();
}

function clearDashboardApiKey() {
    _dashboardApiKey = "";
}

let dashboardApiLast403 = 0;

async function dashboardApiFetch(url, options = {}) {
    const headers = { ...(options.headers || {}) };
    const key = getDashboardApiKey();
    if (key && url.includes("/api/")) headers["X-API-Key"] = key;
    try {
        const res = await fetch(url, { ...options, headers });
        // Auto-prompt on 403: API key may be missing or invalid
        if (res.status === 403) {
            const now = Date.now();
            if (now - dashboardApiLast403 > 15000) {
                dashboardApiLast403 = now;
                const current = getDashboardApiKey();
                const newKey = prompt("API key required. Enter your DataForge API key:", current);
                if (newKey !== null) {
                    setDashboardApiKey(newKey.trim());
                }
            }
        }
        return res;
    } catch (err) {
        throw err;
    }
}

// Configurable API base — supports window.DATAFORGE_API_BASE override, same as app.js
const API_SERVER = (() => {
    const explicit = typeof window.DATAFORGE_API_BASE === 'string' ? window.DATAFORGE_API_BASE.trim() : '';
    if (explicit) return explicit.replace(/\/$/, '');
    const { protocol, hostname, port } = window.location;
    // Only use 127.0.0.1:8000 for dev servers like Vite/Webpack (ports 3000, 5173)
    // Not for nginx port 80 (production) — use same-origin there
    const devPorts = ['3000', '5173'];
    if ((protocol === 'http:' || protocol === 'https:') && (hostname === 'localhost' || hostname === '127.0.0.1') && devPorts.includes(port)) {
        return 'http://127.0.0.1:8000';
    }
    return window.location.origin;
})();

const API_SYSTEM = `${API_SERVER}/api/system`;
const API_SCRAPER = `${API_SERVER}/api/scraper`;

const UPDATE_INTERVAL = (typeof window.DATAFORGE_DASHBOARD_INTERVAL === 'number') ? window.DATAFORGE_DASHBOARD_INTERVAL : 2000;
const MAX_INTERVAL = (typeof window.DATAFORGE_DASHBOARD_MAX_INTERVAL === 'number') ? window.DATAFORGE_DASHBOARD_MAX_INTERVAL : 30000;
let currentInterval = UPDATE_INTERVAL;
let failedPolls = 0;
let pollTimer = null;

let energyChart, communityChart, driftChart;
let historyData = {
    energy: [],
    entropy: [],
    labels: []
};

let topologyHistory = [];
let isLiveMode = true;
let currentReplayIdx = -1;
let activeWaves = []; // Track recent wave_absorption events for animation

function chartDefaults() {
    return {
        responsive: true,
        animation: false,
        plugins: {
            legend: {
                labels: { color: '#9ca3af', boxWidth: 8, font: { size: 10 } }
            }
        },
        scales: {
            x: { ticks: { color: '#4b5563', maxTicksLimit: 6 }, grid: { color: '#111827' } },
            y: { ticks: { color: '#4b5563' }, grid: { color: '#111827' }, beginAtZero: true }
        }
    };
}

function initCharts() {
    const energyCtx = document.getElementById('energy-chart');
    const driftCtx = document.getElementById('drift-chart');
    const communityCtx = document.getElementById('community-chart');

    energyChart = new Chart(energyCtx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                { label: 'Energy', data: [], borderColor: '#facc15', backgroundColor: 'rgba(250,204,21,0.1)', tension: 0.25 },
                { label: 'Entropy', data: [], borderColor: '#f87171', backgroundColor: 'rgba(248,113,113,0.1)', tension: 0.25 }
            ]
        },
        options: chartDefaults()
    });

    driftChart = new Chart(driftCtx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                { label: 'Mean Drift', data: [], borderColor: '#38bdf8', backgroundColor: 'rgba(56,189,248,0.1)', tension: 0.25 }
            ]
        },
        options: chartDefaults()
    });

    communityChart = new Chart(communityCtx, {
        type: 'bar',
        data: {
            labels: [],
            datasets: [
                { label: 'Roles', data: [], backgroundColor: '#22c55e' }
            ]
        },
        options: chartDefaults()
    });
}

function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, (ch) => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
    })[ch]);
}

// Initialize Dashboard
async function init() {
    initCharts();
    setupControls();
    updateLoop(); // start the loop (self-rescheduling with backoff)
}

function setupControls() {
    const scrubber = document.getElementById('timeline-scrubber');
    const liveBtn = document.getElementById('live-mode-btn');

    scrubber.oninput = (e) => {
        isLiveMode = false;
        liveBtn.classList.remove('bg-green-500/10', 'text-green-500', 'border-green-500');
        liveBtn.classList.add('bg-gray-800', 'text-gray-500', 'border-gray-700');
        liveBtn.innerText = "REPLAY";

        currentReplayIdx = parseInt(e.target.value, 10);
        if (topologyHistory[currentReplayIdx]) {
            const topology = topologyHistory[currentReplayIdx].topology || {};
            renderTopology(topology.regions || [], topology.communities || [], []); // Hide edges in replay for now
        }
    };

    liveBtn.onclick = () => {
        isLiveMode = true;
        liveBtn.className = "px-2 py-0.5 border border-green-500 text-[8px] rounded text-green-500 font-bold bg-green-500/10";
        liveBtn.innerText = "LIVE";
        updateLoop(); // Trigger immediate update
    };
}

async function updateLoop() {
    // Use allSettled so individual failures don't crash the whole update
    const results = await Promise.allSettled([
        dashboardApiFetch(`${API_SYSTEM}/topology`).then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); }),
        dashboardApiFetch(`${API_SYSTEM}/observability`).then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); }),
        dashboardApiFetch(`${API_SYSTEM}/history/topology`).then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); }),
        dashboardApiFetch(`${API_SCRAPER}/stats`).then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); }),
        dashboardApiFetch(`${API_SCRAPER}/browser`).then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); }),
        dashboardApiFetch(`${API_SCRAPER}/memory/stats`).then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); }),
        dashboardApiFetch(`${API_SYSTEM}/acquisition/telemetry`).then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); }),
        dashboardApiFetch(`${API_SERVER}/api/system/status`).then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
    ]);

    const [topologyResult, observabilityResult, historyResult, scraperStatsResult, browserStatsResult, memoryStatsResult, acqTelemetryResult, systemStatusResult] = results;

    // Check for rate limiting or other failures
    const anyFailed = results.some(r => r.status === 'rejected');
    if (anyFailed) {
        failedPolls++;
        // Exponential backoff — double interval up to MAX_INTERVAL
        currentInterval = Math.min(UPDATE_INTERVAL * Math.pow(2, failedPolls), MAX_INTERVAL);
        console.warn(`Dashboard poll #${failedPolls} partial failure, backing off to ${currentInterval}ms`);

        document.getElementById('status-badge').innerText = "DEGRADED";
        document.getElementById('status-badge').className = "px-3 py-1 bg-yellow-900/30 text-yellow-400 border border-yellow-800 rounded-full text-xs font-bold";
    } else {
        // Reset backoff on success
        failedPolls = 0;
        currentInterval = UPDATE_INTERVAL;
        document.getElementById('status-badge').innerText = "POLLING VIEW";
        document.getElementById('status-badge').className = "px-3 py-1 bg-green-900/30 text-green-400 border border-green-800 rounded-full text-xs font-bold animate-pulse";
    }

    // Extract values safely — use empty objects for failed fetches
    const topology = topologyResult.status === 'fulfilled' ? topologyResult.value : {};
    const observability = observabilityResult.status === 'fulfilled' ? observabilityResult.value : { health_index: null, telemetry: [] };
    const history = historyResult.status === 'fulfilled' ? historyResult.value : { history: [] };
    const scraperStats = scraperStatsResult.status === 'fulfilled' ? scraperStatsResult.value : null;
    const browserStats = browserStatsResult.status === 'fulfilled' ? browserStatsResult.value : null;
    const memoryStats = memoryStatsResult.status === 'fulfilled' ? memoryStatsResult.value : null;
    const acqTelemetry = acqTelemetryResult.status === 'fulfilled' ? acqTelemetryResult.value : null;
    const systemStatus = systemStatusResult.status === 'fulfilled' ? systemStatusResult.value : null;

    // Update Timeline
    topologyHistory = history.history || [];
    const scrubber = document.getElementById('timeline-scrubber');
    scrubber.max = Math.max(0, topologyHistory.length - 1);

    if (isLiveMode && topologyResult.status === 'fulfilled') {
        updateMetrics(
            topology.metrics || {},
            observability.health_index,
            topology.meso_clusters || [],
            topology.macro_continents || [],
            scraperStats,
            browserStats,
            memoryStats,
            acqTelemetry,
            systemStatus
        );
        renderTopology(
            topology.field_regions || [],
            topology.global_communities || [],
            topology.topology_edges || [],
            topology.meso_clusters || [],
            topology.macro_continents || []
        );
        updateTelemetry(observability.telemetry || []);
        updateCharts(topology.metrics || {}, topology.global_communities || [], topology.drift_logs || {});
        scrubber.value = scrubber.max;
    }

    document.getElementById('last-update').innerText = `LAST SYNC: ${new Date().toLocaleTimeString()}`;

    // Reschedule with backoff
    if (pollTimer) clearTimeout(pollTimer);
    pollTimer = setTimeout(updateLoop, currentInterval);
}

function updateMetrics(m, health, mesoClusters, macroContinents, scraperStats, browserStats, memoryStats, acqTelemetry, systemStatus) {
    m = m || {};
    document.getElementById('metric-pressure').innerText = Number(m.field_pressure || 0).toFixed(3);
    document.getElementById('metric-energy').innerText = Number(m.global_energy || 0).toFixed(3);
    document.getElementById('metric-entropy').innerText = Number(m.global_entropy || 0).toFixed(3);
    document.getElementById('metric-energy-balance').innerText = Number(m.energy_balance || 0).toFixed(4);
    document.getElementById('metric-regions').innerText = Number(m.region_count || 0);
    document.getElementById('metric-meso-count').innerText = Number(mesoClusters ? mesoClusters.length : 0);
    document.getElementById('metric-macro-count').innerText = Number(macroContinents ? macroContinents.length : 0);
    document.getElementById('metric-health').innerText = Number(health ? (health.score || health) : 0).toFixed(2);

    // Scraper Phase 78 Metrics
    if (browserStats) {
        document.getElementById('metric-browser-contexts').innerText = browserStats.active_contexts || 0;
        document.getElementById('metric-browser-reuse').innerText = `Reuse Rate: ${((browserStats.context_reuse_rate || 0) * 100).toFixed(0)}%`;
    }
    if (scraperStats) {
        document.getElementById('metric-latency').innerText = `${(scraperStats.recent_latency_avg || 0).toFixed(0)}ms`;
        document.getElementById('metric-success-rate').innerText = `${((scraperStats.recent_success_rate || 0) * 100).toFixed(0)}%`;
    }
    if (memoryStats) {
        document.getElementById('metric-memory-domains').innerText = memoryStats.domain_count || 0;
    }

    // Acquisition Pipeline Metrics (Phase 92)
    if (acqTelemetry) {
        const t = acqTelemetry;
        document.getElementById('metric-session-bound').innerText = t.session_bound_urls || 0;
        document.getElementById('metric-total-acquisitions').innerText = t.total_acquisitions || 0;

        const rate = t.recovery_success_rate != null ? (t.recovery_success_rate * 100).toFixed(0) : null;
        document.getElementById('metric-recovery-rate').innerText = rate != null ? `${rate}%` : '--%';
        document.getElementById('metric-recovery-detail').innerText = `${t.recovery_successes || 0} / ${t.recovery_attempts || 0} attempts`;

        const emptyCount = (t.state_distribution && t.state_distribution.empty_response) || 0;
        document.getElementById('metric-empty-200').innerText = emptyCount;

        // Acquisition mode distribution
        const dist = t.state_distribution || {};
        const modes = [];
        if (dist.direct) modes.push(`direct:${dist.direct}`);
        if (dist.recovered) modes.push(`recovered:${dist.recovered}`);
        if (dist.session_expired) modes.push(`expired:${dist.session_expired}`);
        if (dist.empty_response) modes.push(`empty:${dist.empty_response}`);
        if (dist.awaiting_search_params) modes.push(`awaiting:${dist.awaiting_search_params}`);
        document.getElementById('metric-acq-modes').innerText = modes.length ? modes.join('  ') : '--';

        // Color-code recovery rate
        const recoveryEl = document.getElementById('metric-recovery-rate');
        if (rate != null) {
            if (rate >= 80) recoveryEl.className = 'metric-value text-green-500';
            else if (rate >= 40) recoveryEl.className = 'metric-value text-yellow-500';
            else recoveryEl.className = 'metric-value text-red-500';
        }

        // Style empty-200 count
        const emptyEl = document.getElementById('metric-empty-200');
        if (emptyCount > 0) emptyEl.className = 'metric-value text-red-500';
    }

    if (systemStatus) {
        const jobs = systemStatus.jobs || {};
        document.getElementById('metric-jobs-completed').innerText = jobs.completed || 0;
        document.getElementById('metric-jobs-degraded').innerText = jobs.degraded || 0;
        document.getElementById('metric-jobs-empty-result').innerText = jobs.empty_result || 0;
        document.getElementById('metric-jobs-failed').innerText = jobs.failed || 0;
    }

    // Style energy balance based on conservation status
    const balanceEl = document.getElementById('metric-energy-balance');
    const balanceVal = Number(m.energy_balance || 0);
    if (Math.abs(balanceVal) < 0.01) {
        balanceEl.className = 'metric-value text-green-500';  // conserved
    } else if (Math.abs(balanceVal) < 0.1) {
        balanceEl.className = 'metric-value text-yellow-500';  // slight drift
    } else {
        balanceEl.className = 'metric-value text-red-500';     // conservation violation
    }

    if (health) {
        document.getElementById('metric-health').innerText = Number(health.score || 0).toFixed(2);
        const statusEl = document.getElementById('health-status');
        const metrics = health.metrics || {};
        const monocultureRisk = Number(metrics.monoculture_risk || 0);
        const diversity = Number(metrics.diversity || 0);
        const alert = monocultureRisk > 0.5 ? "MONOCULTURE RISK" : (health.status || 'unknown');
        statusEl.innerText = `${alert} // DR: ${diversity.toFixed(2)}`;
        statusEl.className = (health.status === 'optimal' && monocultureRisk < 0.5) ? 'text-[10px] text-green-500 mt-1 uppercase' :
                             (health.status === 'degraded' || monocultureRisk >= 0.5) ? 'text-[10px] text-yellow-500 mt-1 uppercase' :
                             'text-[10px] text-red-500 mt-1 uppercase';
    }
}

function renderTopology(regions, communities, edges, mesoClusters, macroContinents) {
    const svg = document.getElementById('field-svg');
    svg.innerHTML = ''; // Clear

    _renderTopologyInternal(regions, communities, edges, mesoClusters, macroContinents);
}

function _renderTopologyInternal(regions, communities, edges, mesoClusters, macroContinents) {
    const svg = document.getElementById('field-svg');
    if (!regions || regions.length === 0) {
        const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
        text.setAttribute("x", "50%");
        text.setAttribute("y", "50%");
        text.setAttribute("text-anchor", "middle");
        text.setAttribute("fill", "#333");
        text.textContent = "FIELD VOID — NO ACTIVE BASINS";
        svg.appendChild(text);
        return;
    }

    const width = 800;
    const height = 450;
    const colors = ['#00ff41', '#007fff', '#ff003c', '#ffbf00', '#9d00ff', '#00ffd0'];
    const macroColors = ['rgba(0,255,65,0.04)', 'rgba(0,127,255,0.04)', 'rgba(255,0,60,0.04)', 'rgba(255,191,0,0.04)', 'rgba(157,0,255,0.04)', 'rgba(0,255,208,0.04)'];
    const mesoColors = ['rgba(0,255,65,0.08)', 'rgba(0,127,255,0.08)', 'rgba(255,0,60,0.08)', 'rgba(255,191,0,0.08)', 'rgba(157,0,255,0.08)', 'rgba(0,255,208,0.08)'];

    const getPos = (id) => {
        const hash = id.split('').reduce((a, b) => { a = ((a << 5) - a) + b.charCodeAt(0); return a & a; }, 0);
        return {
            x: 100 + (Math.abs(hash) % (width - 200)),
            y: 100 + (Math.abs(hash * 7) % (height - 200))
        };
    };

    // Build region position map
    const regionPositions = {};
    regions.forEach(r => {
        regionPositions[r.region_id] = getPos(r.region_id);
    });

    // ─── MACRO CONTINENTS (Background) ───
    // Draw large-scale continent shapes first (bottom layer)
    if (macroContinents && macroContinents.length > 0) {
        macroContinents.forEach((cont, idx) => {
            // Find all region positions belonging to this continent's meso clusters
            const continentPoints = [];
            if (mesoClusters) {
                mesoClusters.forEach(cluster => {
                    if ((cont.meso_cluster_ids || []).includes(cluster.cluster_id)) {
                        (cluster.region_ids || []).forEach(rid => {
                            const pos = regionPositions[rid];
                            if (pos) continentPoints.push(pos);
                        });
                    }
                });
            }
            if (continentPoints.length < 3) return;

            // Compute convex hull
            const hull = convexHull(continentPoints);
            if (!hull || hull.length < 3) return;

            const poly = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
            const points = hull.map(p => `${p.x},${p.y}`).join(' ');
            poly.setAttribute("points", points);
            const colorIdx = idx % macroColors.length;
            poly.setAttribute("fill", macroColors[colorIdx]);
            poly.setAttribute("stroke", colors[colorIdx]);
            poly.setAttribute("stroke-width", "1");
            poly.setAttribute("stroke-dasharray", "4,4");
            poly.setAttribute("stroke-opacity", "0.2");
            poly.setAttribute("class", "macro-continent");

            // Add continent label
            const cx = hull.reduce((s, p) => s + p.x, 0) / hull.length;
            const cy = hull.reduce((s, p) => s + p.y, 0) / hull.length;

            const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
            label.setAttribute("x", cx);
            label.setAttribute("y", cy - 5);
            label.setAttribute("text-anchor", "middle");
            label.setAttribute("fill", colors[colorIdx]);
            label.setAttribute("font-size", "6");
            label.setAttribute("fill-opacity", "0.35");
            label.textContent = `${cont.continent_id} (P:${cont.pressure})`;

            svg.appendChild(poly);
            svg.appendChild(label);
        });
    }

    // ─── MESO CLUSTERS (Intermediate Background) ───
    // Draw meso cluster hulls
    if (mesoClusters && mesoClusters.length > 0) {
        mesoClusters.forEach((cluster, idx) => {
            const clusterPoints = [];
            (cluster.region_ids || []).forEach(rid => {
                const pos = regionPositions[rid];
                if (pos) clusterPoints.push(pos);
            });
            if (clusterPoints.length < 3) return;

            const hull = convexHull(clusterPoints);
            if (!hull || hull.length < 3) return;

            const poly = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
            const points = hull.map(p => `${p.x},${p.y}`).join(' ');
            poly.setAttribute("points", points);
            const colorIdx = idx % mesoColors.length;
            poly.setAttribute("fill", mesoColors[colorIdx]);
            poly.setAttribute("stroke", colors[colorIdx]);
            poly.setAttribute("stroke-width", "0.5");
            poly.setAttribute("stroke-opacity", "0.3");
            poly.setAttribute("class", "meso-cluster");

            // Tooltip hover
            poly.onmouseover = () => showMesoClusterDetails(cluster);

            // Label
            const cx = hull.reduce((s, p) => s + p.x, 0) / hull.length;
            const cy = hull.reduce((s, p) => s + p.y, 0) / hull.length;

            const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
            label.setAttribute("x", cx);
            label.setAttribute("y", cy);
            label.setAttribute("text-anchor", "middle");
            label.setAttribute("fill", colors[colorIdx]);
            label.setAttribute("font-size", "7");
            label.setAttribute("fill-opacity", "0.5");
            label.textContent = `${cluster.shared_roles && cluster.shared_roles[0] || 'cluster'} (${cluster.size})`;

            svg.appendChild(poly);
            svg.appendChild(label);
        });
    }

    // 1. Draw Cohesion Edges (Relational Web with Pressure)
    if (edges) {
        edges.forEach(e => {
            const r1 = regions.find(r => (r.competing_roles || []).includes(e.source));
            const r2 = regions.find(r => (r.competing_roles || []).includes(e.target));
            if (r1 && r2) {
                const p1 = regionPositions[r1.region_id];
                const p2 = regionPositions[r2.region_id];
                if (p1 && p2) {
                    const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
                    line.setAttribute("x1", p1.x);
                    line.setAttribute("y1", p1.y);
                    line.setAttribute("x2", p2.x);
                    line.setAttribute("y2", p2.y);

                    // Pressure-aware styling
                    const pressure = e.pressure || 0;
                    if (pressure > 0.7) {
                        line.setAttribute("class", "edge-pressure-high");
                    } else if (pressure > 0.3) {
                        line.setAttribute("class", "edge-pressure-med");
                    } else {
                        line.setAttribute("class", "edge-pressure-low");
                    }

                    line.setAttribute("stroke-width", (e.weight || 0.1) * 6);
                    line.setAttribute("stroke-opacity", Math.max(0.1, (e.weight || 0.1)));
                    svg.appendChild(line);
                }
            }
        });
    }

    // 2. Draw Waves (Ripples)
    activeWaves.forEach(w => {
        const pos = regionPositions[w.id];
        if (pos) {
            const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
            circle.setAttribute("cx", pos.x);
            circle.setAttribute("cy", pos.y);
            circle.setAttribute("r", 5);
            circle.setAttribute("class", "wave-ripple");
            circle.style.strokeWidth = `${Math.max(1, w.intensity * 3)}px`;
            svg.appendChild(circle);

            // Draw connection to source if available
            const sourcePos = regionPositions[w.source];
            if (sourcePos) {
                const beam = document.createElementNS("http://www.w3.org/2000/svg", "line");
                beam.setAttribute("x1", sourcePos.x);
                beam.setAttribute("y1", sourcePos.y);
                beam.setAttribute("x2", pos.x);
                beam.setAttribute("y2", pos.y);
                beam.setAttribute("stroke", "#00ff41");
                beam.setAttribute("stroke-width", Math.max(1, w.intensity * 2));
                beam.setAttribute("stroke-opacity", "0.3");
                beam.setAttribute("stroke-dasharray", "2,2");
                svg.appendChild(beam);
            }
        }
    });

    // 3. Draw Regions (Attractor Nodes)
    regions.forEach((r, i) => {
        const radius = 5 + (Number(r.local_energy || 0) * 20);
        const opacity = 0.2 + (Number(r.integrity || 0) * 0.8);
        const {x: cx, y: cy} = regionPositions[r.region_id];
        if (cx === undefined) return;

        let color = '#555';
        if (communities && communities.length > 0) {
            communities.forEach((c, idx) => {
                if (c.some(role => (r.competing_roles || []).includes(role))) {
                    color = colors[idx % colors.length];
                }
            });
        }

        const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
        circle.setAttribute("cx", cx);
        circle.setAttribute("cy", cy);
        circle.setAttribute("r", radius);
        circle.setAttribute("fill", color);
        circle.setAttribute("fill-opacity", opacity);
        circle.setAttribute("stroke", color);
        circle.setAttribute("stroke-width", Number(r.instability || 0) > 0.5 ? "2" : "0.5");
        circle.setAttribute("class", "topology-node");

        if (Number(r.instability || 0) > 0.8) {
            const animate = document.createElementNS("http://www.w3.org/2000/svg", "animate");
            animate.setAttribute("attributeName", "r");
            animate.setAttribute("values", `${radius};${radius * 1.5};${radius}`);
            animate.setAttribute("dur", "1s");
            animate.setAttribute("repeatCount", "indefinite");
            circle.appendChild(animate);
        }

        circle.onmouseover = () => showRegionDetails(r);
        svg.appendChild(circle);

        if (Number(r.integrity || 0) > 0.7) {
            const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
            label.setAttribute("x", cx);
            label.setAttribute("y", cy + radius + 12);
            label.setAttribute("text-anchor", "middle");
            label.setAttribute("fill", "#999");
            label.setAttribute("font-size", "8");
            label.textContent = (r.competing_roles || [])[0] || 'anon';
            svg.appendChild(label);
        }
    });
}

function showRegionDetails(r) {
    const el = document.getElementById('region-details');
    const content = document.getElementById('region-info-content');
    el.classList.remove('hidden');

    content.innerHTML = `
        <div class="flex justify-between mb-1"><span>ID:</span> <span class="text-white">${escapeHtml(r.region_id)}</span></div>
        <div class="flex justify-between mb-1"><span>ROLES:</span> <span class="text-white">${escapeHtml((r.competing_roles || []).join(', '))}</span></div>
        <div class="flex justify-between mb-1"><span>TOKEN:</span> <span class="text-white truncate" style="max-width: 100px;">"${escapeHtml(r.token)}"</span></div>
        <div class="flex justify-between mb-1"><span>INSTABILITY:</span> <span class="text-red-400">${Number(r.instability || 0).toFixed(3)}</span></div>
        <div class="flex justify-between mb-1"><span>ENERGY:</span> <span class="text-yellow-400">${Number(r.local_energy || 0).toFixed(3)}</span></div>
        <div class="flex justify-between mb-1"><span>INTEGRITY:</span> <span class="text-green-400">${Number(r.integrity || 0).toFixed(3)}</span></div>
    `;
}

function showMesoClusterDetails(cluster) {
    const el = document.getElementById('region-details');
    const content = document.getElementById('region-info-content');
    el.classList.remove('hidden');

    content.innerHTML = `
        <div class="text-yellow-400 text-[9px] font-bold mb-2">MESO CLUSTER</div>
        <div class="flex justify-between mb-1"><span>ID:</span> <span class="text-white">${escapeHtml(cluster.cluster_id)}</span></div>
        <div class="flex justify-between mb-1"><span>SIZE:</span> <span class="text-white">${cluster.size} regions</span></div>
        <div class="flex justify-between mb-1"><span>POLICY:</span> <span class="text-cyan-400">${escapeHtml(cluster.interaction_policy)}</span></div>
        <div class="flex justify-between mb-1"><span>INSTABILITY:</span> <span class="text-red-400">${Number(cluster.avg_instability || 0).toFixed(3)}</span></div>
        <div class="flex justify-between mb-1"><span>ENTROPY:</span> <span class="text-orange-400">${Number(cluster.entropy || 0).toFixed(3)}</span></div>
        <div class="flex justify-between mb-1"><span>DRIFT:</span> <span class="text-blue-400">${Number(cluster.drift || 0).toFixed(3)}</span></div>
        <div class="flex justify-between mb-1"><span>STABILITY:</span> <span class="text-green-400">${Number(cluster.stability || 0).toFixed(3)}</span></div>
        <div class="flex justify-between mb-1"><span>BOUNDARY:</span> <span class="text-purple-400">${Number(cluster.boundary_strength || 0).toFixed(3)}</span></div>
        <div class="flex justify-between mb-1"><span>SHARED:</span> <span class="text-white">${escapeHtml((cluster.shared_roles || []).join(', '))}</span></div>
    `;
}

// Convex Hull (Monotone Chain)
function convexHull(points) {
    if (points.length < 3) return null;
    const sorted = points.slice().sort((a, b) => a.x - b.x || a.y - b.y);
    const lower = [];
    for (const p of sorted) {
        while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) {
            lower.pop();
        }
        lower.push(p);
    }
    const upper = [];
    for (const p of sorted.reverse()) {
        while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) {
            upper.pop();
        }
        upper.push(p);
    }
    lower.pop();
    upper.pop();
    return lower.concat(upper);
}

function cross(o, a, b) {
    return (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x);
}

function updateTelemetry(events) {
    const log = document.getElementById('telemetry-log');
    if (!events) return;

    // Capture new wave events for animation
    const now = Date.now();
    events.forEach(e => {
        if (e.type === 'wave_absorption' && (now - e.timestamp * 1000) < UPDATE_INTERVAL * 2) {
            if (!activeWaves.some(w => w.id === e.details.region_id && Math.abs(w.time - e.timestamp) < 0.1)) {
                activeWaves.push({
                    id: e.details.region_id,
                    source: e.details.source_id,
                    intensity: e.details.intensity,
                    time: e.timestamp,
                    expire: now + 3000 // Animation duration
                });
            }
        }
    });
    // Clean up expired waves
    activeWaves = activeWaves.filter(w => w.expire > now);

    log.innerHTML = events.map(e => {
        const color = e.type === 'degradation' ? 'text-red-500' :
                      e.type === 'transaction' ? 'text-blue-400' :
                      e.type === 'wave_absorption' ? 'text-green-400' :
                      e.type === 'scrape' ? 'text-cyan-400' : 'text-gray-500';
        const icon = e.type === 'degradation' ? '⚠' :
                     e.type === 'wave_absorption' ? '⌇' :
                     e.type === 'scrape' ? '⚓' : '◈';

        let detailsStr = '';
        if (e.type === 'scrape') {
            const d = e.details || {};
            detailsStr = `Records: ${d.records} | Fetch: ${d.fetch_ms?.toFixed(0)}ms (${d.fallback_type || 'none'}) | HR: ${(d.selector_hit_rate*100)?.toFixed(0)}% | R: ${d.retries} | AB: ${d.anti_bot.toFixed(2)}`;
        }
 else {
            detailsStr = JSON.stringify(e.details || {}).substring(0, 80);
        }

        return `<div class="border-l border-gray-800 pl-2 py-1">
            <span class="${color} font-bold mr-2">${icon} [${escapeHtml(e.subsystem || e.type)}]</span>
            <span class="text-gray-400">${escapeHtml(e.action || e.label || '')}</span>
            <div class="text-[8px] text-gray-700 mt-1">${escapeHtml(detailsStr)}...</div>
        </div>`;
    }).reverse().join('');
}

function updateCharts(m, communities, driftLogs) {
    communities = communities || [];
    // Energy Chart
    energyChart.data.labels.push("");
    energyChart.data.datasets[0].data.push(m.global_energy);
    energyChart.data.datasets[1].data.push(m.global_entropy);

    if (energyChart.data.labels.length > 50) {
        energyChart.data.labels.shift();
        energyChart.data.datasets[0].data.shift();
        energyChart.data.datasets[1].data.shift();
    }
    energyChart.update('none');

    // Drift Chart
    let totalDrift = 0;
    let driftCount = 0;
    Object.values(driftLogs || {}).forEach(log => {
        if (log && log.length > 0) {
            totalDrift += log[log.length - 1];
            driftCount++;
        }
    });
    const meanDrift = driftCount > 0 ? totalDrift / driftCount : 0;

    driftChart.data.labels.push("");
    driftChart.data.datasets[0].data.push(meanDrift);
    if (driftChart.data.labels.length > 50) {
        driftChart.data.labels.shift();
        driftChart.data.datasets[0].data.shift();
    }
    driftChart.update('none');

    // Community Chart
    communityChart.data.labels = communities.map((c, i) => `C-${i}`);
    communityChart.data.datasets[0].data = communities.map(c => c.length);
    communityChart.update('none');
}

document.addEventListener('DOMContentLoaded', init);
