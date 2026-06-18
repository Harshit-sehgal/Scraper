/**
 * Vitest tests for the System Info panel.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";

describe("system-info module", () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <span id="sysinfo-jobs-total"></span>
      <span id="sysinfo-jobs-active"></span>
      <span id="sysinfo-jobs-completed"></span>
      <span id="sysinfo-jobs-failed"></span>
      <span id="sysinfo-recycle"></span>
      <span id="sysinfo-backend"></span>
      <span id="sysinfo-refreshed-at"></span>
      <span id="sysinfo-queue-pending"></span>
      <span id="sysinfo-queue-running"></span>
      <span id="sysinfo-queue-dead-letter"></span>
      <span id="sysinfo-queue-max"></span>
      <div id="sysinfo-workers"></div>
      <div id="sysinfo-error"></div>
    `;
  });

  afterEach(() => {
    document.body.innerHTML = "";
    vi.resetModules();
    vi.unstubAllGlobals();
  });

  it("exports refreshSystemInfo, startSystemInfo, stopSystemInfo", async () => {
    const mod = await import("./system-info.js");
    expect(typeof mod.refreshSystemInfo).toBe("function");
    expect(typeof mod.startSystemInfo).toBe("function");
    expect(typeof mod.stopSystemInfo).toBe("function");
  });

  it("F-002: reads job counts from status.jobs.* (not status.total_jobs/counts)", async () => {
    // The backend GET /api/system/status returns:
    //   { jobs: { total, active, completed, failed, ... }, recycle_bin_count, ... }
    // Before the fix, _setKpis read status.total_jobs / status.counts and
    // left 4/6 KPIs stuck at "—".
    vi.doMock("./api.js", () => ({
      apiFetch: vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            jobs: { total: 42, active: 3, completed: 35, failed: 4 },
            recycle_bin_count: 7,
            backend: "sqlite",
            queue: { pending: 1, running: 2, dead_letter: 0, max_concurrency: 4 },
            workers: [],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ),
      getSessionRole: () => "admin",
    }));
    const mod = await import("./system-info.js");
    await mod.refreshSystemInfo();
    expect(document.getElementById("sysinfo-jobs-total").textContent).toBe("42");
    expect(document.getElementById("sysinfo-jobs-active").textContent).toBe("3");
    expect(document.getElementById("sysinfo-jobs-completed").textContent).toBe("35");
    expect(document.getElementById("sysinfo-jobs-failed").textContent).toBe("4");
    expect(document.getElementById("sysinfo-recycle").textContent).toBe("7");
    expect(document.getElementById("sysinfo-backend").textContent).toBe("sqlite");
  });
});
