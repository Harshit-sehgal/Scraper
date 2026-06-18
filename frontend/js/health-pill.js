/* ═══════════════════════════════════
   DataForge — Topbar health pill
   ═══════════════════════════════════ */

import { API } from "./api.js";

const REFRESH_MS = 30_000;
const PROBE_TIMEOUT_MS = 5_000;

let timer = null;
let lastStatus = "unknown";
let lastError = "";

/** Render the health pill into the topbar element. */
function setPill(state, label) {
  const el = document.getElementById("health-pill");
  if (!el) return;
  el.dataset.state = state;
  el.title = label;
  el.textContent = label;
}

/** Probe /api/health and /api/ready in parallel; update the pill. */
async function probe() {
  const ac = new AbortController();
  const timeout = setTimeout(() => ac.abort(), PROBE_TIMEOUT_MS);
  try {
    const [live, ready] = await Promise.all([
      fetch(`${API}/api/health`, { signal: ac.signal, credentials: "include" })
        .then((r) => r.status)
        .catch(() => 0),
      fetch(`${API}/api/ready`, { signal: ac.signal, credentials: "include" })
        .then((r) => r.status)
        .catch(() => 0),
    ]);
    if (live === 200 && ready === 200) {
      lastStatus = "healthy";
      lastError = "";
      setPill("healthy", "API healthy");
    } else if (live === 200 && ready !== 200) {
      lastStatus = "degraded";
      lastError = `ready=${ready}`;
      setPill("degraded", `API live, /ready=${ready}`);
    } else {
      lastStatus = "down";
      lastError = `health=${live} ready=${ready}`;
      setPill("down", `API unreachable (health=${live} ready=${ready})`);
    }
  } finally {
    clearTimeout(timeout);
  }
}

/** Start the periodic health probe (idempotent). */
export function startHealthPill() {
  if (timer) return;
  // Probe immediately, then every REFRESH_MS.
  void probe();
  timer = setInterval(() => {
    void probe();
  }, REFRESH_MS);
}

/** Stop the periodic probe (mostly for tests). */
export function stopHealthPill() {
  if (timer) {
    clearInterval(timer);
    timer = null;
  }
}

/** Read-only accessor for tests and other UI components. */
export function getHealthState() {
  return { status: lastStatus, error: lastError };
}
