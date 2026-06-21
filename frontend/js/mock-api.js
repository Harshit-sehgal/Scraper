/* Mock API adapter for frontend-first development.
   Enabled only when window.DATAFORGE_USE_MOCKS === true. */

import { normalizeApiPath } from "./api-contract.js";

const MOCK_BASE = new URL("../mocks/", import.meta.url);

const FALLBACK_JOBS = {
  jobs: [
    {
      id: "mock-completed-1",
      name: "Demo directory scrape",
      mode: "manual",
      status: "completed",
      created_at: "2026-06-20T09:15:00Z",
      urls: ["https://example.com/directory"],
      total_records: 3,
      filtered_records: 3,
      progress_current: 3,
      progress_total: 3,
      error: "",
      warnings: [],
    },
    {
      id: "mock-running-1",
      name: "Supplier leads",
      mode: "auto",
      status: "running",
      created_at: "2026-06-20T10:05:00Z",
      urls: ["https://example.com/suppliers", "https://example.org/vendors"],
      total_records: 9,
      filtered_records: 7,
      progress_current: 2,
      progress_total: 5,
      error: "",
      warnings: ["One source returned no matching rows"],
    },
  ],
};

const FALLBACK_DETAIL = {
  id: "mock-completed-1",
  name: "Demo directory scrape",
  mode: "manual",
  status: "completed",
  created_at: "2026-06-20T09:15:00Z",
  urls: ["https://example.com/directory"],
  total_records: 3,
  filtered_records: 3,
  progress_current: 3,
  progress_total: 3,
  error: "",
  logs: [
    { timestamp: "2026-06-20T09:15:05Z", level: "info", message: "Queued job" },
    { timestamp: "2026-06-20T09:15:12Z", level: "info", message: "Extracted records" },
  ],
  quality_report: {
    overall_score: 0.91,
    avg_record_score: 0.9,
    records_below_threshold: 0,
  },
};

const FALLBACK_RESULTS = {
  results: [
    {
      company_name: "Northstar Studio",
      email: "hello@northstar.example",
      phone: "+1 555 0101",
      website: "https://northstar.example",
      source_url: "https://example.com/directory/northstar",
      record_score: 0.94,
    },
    {
      company_name: "Cedar Analytics",
      email: "team@cedar.example",
      phone: "+1 555 0102",
      website: "https://cedar.example",
      source_url: "https://example.com/directory/cedar",
      record_score: 0.89,
    },
  ],
};

const FALLBACK_STATUS = {
  jobs: {
    total: 2,
    active: 1,
    running: 1,
    completed: 1,
    failed: 0,
  },
  queue: {
    pending: 0,
    running: 1,
  },
  workers: {
    active: 1,
    total: 1,
  },
};

let statePromise = null;

export function isMockMode() {
  if (typeof window === "undefined") return false;
  return window.DATAFORGE_USE_MOCKS === true;
}

function getScenario() {
  if (typeof window === "undefined") return "";
  return String(window.DATAFORGE_MOCK_SCENARIO || "");
}

async function readMockJson(fileName, fallback) {
  try {
    const res = await fetch(new URL(fileName, MOCK_BASE));
    if (res.ok) return await res.json();
  } catch {
    // Fall back to embedded fixtures when static mocks are unavailable.
  }
  return structuredClone(fallback);
}

async function getState() {
  if (!statePromise) {
    statePromise = Promise.all([
      readMockJson("jobs.json", FALLBACK_JOBS),
      readMockJson("job-detail.json", FALLBACK_DETAIL),
      readMockJson("results.json", FALLBACK_RESULTS),
      readMockJson("system-status.json", FALLBACK_STATUS),
    ]).then(([jobs, detail, results, status]) => ({
      jobs: Array.isArray(jobs.jobs) ? jobs.jobs : [],
      detail,
      results: Array.isArray(results.results) ? results.results : [],
      status,
      nextId: 1,
    }));
  }
  return statePromise;
}

function jsonResponse(body, init = {}) {
  return new Response(JSON.stringify(body), {
    status: init.status || 200,
    headers: { "Content-Type": "application/json", ...(init.headers || {}) },
  });
}

function textResponse(body, contentType) {
  return new Response(body, {
    status: 200,
    headers: { "Content-Type": contentType },
  });
}

async function parseBody(options) {
  if (!options || !options.body) return {};
  try {
    return JSON.parse(options.body);
  } catch {
    return {};
  }
}

function findJob(state, id) {
  return state.jobs.find((job) => String(job.id) === String(id)) || null;
}

function buildDetail(state, id) {
  const scenario = getScenario();
  const job = findJob(state, id) || state.detail;
  const rows = scenario === "empty-results" ? [] : state.results;
  return {
    ...state.detail,
    ...job,
    id: job.id || id,
    results: rows,
    total_records: rows.length,
    filtered_records: rows.length,
  };
}

function rowsToCsv(rows) {
  if (!rows.length) return "";
  const keys = Array.from(
    rows.reduce((set, row) => Object.keys(row || {}).reduce((acc, key) => acc.add(key), set), new Set()),
  );
  const escapeCell = (value) => {
    const text = String(value ?? "");
    return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  };
  return [keys.join(","), ...rows.map((row) => keys.map((key) => escapeCell(row[key])).join(","))].join("\n");
}

export async function maybeHandleMockRequest(input, options = {}) {
  if (!isMockMode()) return null;

  const method = String(options.method || "GET").toUpperCase();
  const pathWithQuery = normalizeApiPath(input);
  const [path] = pathWithQuery.split("?");
  const state = await getState();
  const scenario = getScenario();

  if (scenario === "api-failure") {
    return jsonResponse({ detail: "Mock API failure" }, { status: 503 });
  }

  if (method === "GET" && (path === "/api/health" || path === "/api/ready")) {
    return jsonResponse({ status: "ok" });
  }

  if (method === "GET" && path === "/api/system/status") {
    return jsonResponse(state.status);
  }

  if (method === "GET" && path === "/api/jobs") {
    return jsonResponse({ jobs: scenario === "empty-jobs" ? [] : state.jobs });
  }

  if (method === "POST" && path === "/api/jobs") {
    const payload = await parseBody(options);
    const id = `mock-created-${state.nextId++}`;
    const job = {
      id,
      name: payload.name || "Mock scrape job",
      mode: payload.mode || "manual",
      status: "running",
      created_at: new Date().toISOString(),
      urls: Array.isArray(payload.urls) ? payload.urls : [],
      total_records: 0,
      filtered_records: 0,
      progress_current: 1,
      progress_total: 4,
      error: "",
      warnings: [],
    };
    state.jobs.unshift(job);
    return jsonResponse(job, { status: 201 });
  }

  const jobMatch = path.match(/^\/api\/jobs\/([^/]+)(?:\/(.+))?$/);
  if (jobMatch) {
    const id = decodeURIComponent(jobMatch[1]);
    const suffix = jobMatch[2] || "";

    if (method === "POST" && suffix === "cancel") {
      const job = findJob(state, id);
      if (job) job.status = "canceled";
      return jsonResponse({ message: "Cancellation requested" });
    }

    if (method === "DELETE" && !suffix) {
      state.jobs = state.jobs.filter((job) => String(job.id) !== String(id));
      return jsonResponse({ message: "Job deleted" });
    }

    if (method === "GET" && suffix.startsWith("export/")) {
      const rows = buildDetail(state, id).results || [];
      if (suffix === "export/json") return textResponse(JSON.stringify(rows, null, 2), "application/json");
      if (suffix === "export/csv") return textResponse(rowsToCsv(rows), "text/csv");
      if (suffix === "export/excel") return textResponse(rowsToCsv(rows), "text/csv");
    }

    if (method === "GET" && !suffix) {
      return jsonResponse(buildDetail(state, id));
    }
  }

  if (method === "POST" && path === "/api/discover") {
    return jsonResponse({
      urls: [
        {
          url: "https://example.com/directory",
          title: "Example directory",
          reason: "Mock source with repeated business listings",
        },
        {
          url: "https://example.org/vendors",
          title: "Example vendors",
          reason: "Secondary source for coverage",
        },
      ],
    });
  }

  if (method === "POST" && path === "/api/schema/suggest") {
    return jsonResponse({
      topic: "business directory leads",
      location: "United States",
      fields: [
        { name: "company_name", field_type: "string", description: "Business name" },
        { name: "email", field_type: "email", description: "Contact email" },
        { name: "phone", field_type: "phone", description: "Contact phone" },
        { name: "source_url", field_type: "url", description: "Page where the record was found" },
      ],
      notes: "Mock schema generated from frontend-only data.",
    });
  }

  if (method === "POST" && path === "/api/url/analyze") {
    return jsonResponse({
      page_structure: "listing",
      structure_confidence: 0.92,
      estimated_record_count: 24,
      anti_bot_score: 0.12,
      fetch_time_ms: 420,
      item_container: ".listing-card",
      suggested_fields: [
        { name: "company_name", type: "string", selector: ".listing-title" },
        { name: "email", type: "email", selector: "a[href^='mailto:']" },
        { name: "phone", type: "phone", selector: ".phone" },
      ],
      url_intelligence: {
        classification: "public_directory",
        confidence: 0.92,
        risk: "low",
        recommended_mode: "direct_scrape",
        reason: "Mock public directory page with visible listing cards.",
        next_steps: ["Review detected fields", "Start a mock scrape", "Inspect the results table"],
      },
    });
  }

  return jsonResponse({ detail: `No mock response configured for ${method} ${path}` }, { status: 404 });
}
