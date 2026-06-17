/**
 * Vitest tests for the System Info panel.
 */
import { describe, it, expect, beforeEach, afterEach } from "vitest";

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
  });

  it("exports refreshSystemInfo, startSystemInfo, stopSystemInfo", async () => {
    const mod = await import("./system-info.js");
    expect(typeof mod.refreshSystemInfo).toBe("function");
    expect(typeof mod.startSystemInfo).toBe("function");
    expect(typeof mod.stopSystemInfo).toBe("function");
  });
});
